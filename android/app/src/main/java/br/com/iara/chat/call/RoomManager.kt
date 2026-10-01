package br.com.iara.chat.call

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import br.com.iara.chat.data.AuthStore
import br.com.iara.chat.data.TokenApiFactory
import br.com.iara.chat.data.TokenRequest
import br.com.iara.chat.data.TokenResponse
import io.livekit.android.LiveKit
import io.livekit.android.LiveKitOverrides
import io.livekit.android.AudioOptions
import io.livekit.android.RoomOptions
import io.livekit.android.events.RoomEvent
import io.livekit.android.events.collect
import io.livekit.android.renderer.TextureViewRenderer
import io.livekit.android.room.Room
import io.livekit.android.room.participant.Participant
import io.livekit.android.room.track.LocalAudioTrackOptions
import io.livekit.android.room.track.VideoTrack
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import retrofit2.HttpException
import java.util.UUID

/**
 * Dono do ciclo de vida da sala LiveKit.
 *
 * O app e um cliente fino de proposito: nenhuma regra de conversa, nenhum
 * prompt, nenhuma chave de fornecedor. Ele pede um token, entra na sala,
 * publica o microfone e desenha o primeiro video remoto que aparecer.
 */
class RoomManager(application: Application) : AndroidViewModel(application) {

    private companion object {
        const val TAG = "RoomManager"

        /**
         * A conta vale, mas a empresa nao pode abrir conversa agora: codigo
         * revogado, vencido, ou teto de minutos atingido. Nao distinguimos os
         * tres aqui porque a pessoa resolve do mesmo jeito, falando com quem
         * contratou. O motivo real fica no log do servidor.
         */
        const val SEM_SALDO =
            "A sua empresa esta sem acesso no momento. Fale com quem contratou a IARA."
        const val AGENT_STATE_ATTRIBUTE = "lk.agent.state"
        const val APP_READY_ATTRIBUTE = "app.avatar_ready"

        /** Espera entre tentativas de reconexao, em ms. */
        val RECONNECT_BACKOFF = longArrayOf(1_000, 3_000, 7_000)
    }

    private val _state = MutableStateFlow(CallUiState())
    val state: StateFlow<CallUiState> = _state.asStateFlow()

    private val tokenApi = TokenApiFactory.create()

    /** Sessao de quem entrou. O /token so responde com ela. */
    private val auth = AuthStore(application)

    /** Avisado quando o servidor recusa a sessao, para voltar a tela de entrada. */
    var onSessionExpired: (() -> Unit)? = null

    private var room: Room? = null
    private var eventJob: Job? = null
    private var timerJob: Job? = null
    private var credentials: TokenResponse? = null
    private var userInitiatedEnd = false

    /** Quem publica o video do avatar. E dele que vem o sinal de fala real. */
    private var avatarIdentity: String? = null
    private var reconnectAttempt = 0

    // -- entrada -------------------------------------------------------

    fun start() {
        if (_state.value.phase == CallPhase.Connecting ||
            _state.value.phase == CallPhase.Active
        ) {
            return
        }

        userInitiatedEnd = false
        reconnectAttempt = 0
        _state.value = CallUiState(phase = CallPhase.Connecting)

        viewModelScope.launch {
            val creds = try {
                tokenApi.createToken(
                    bearer = "Bearer " + auth.sessionToken.orEmpty(),
                    request = TokenRequest(userId = UUID.randomUUID().toString()),
                )
            } catch (t: Throwable) {
                Log.e(TAG, "falha ao obter token", t)
                when {
                    // 401: a sessao morreu no servidor. Devolve a pessoa para a
                    // tela de entrada em vez de deixar ela tentando de novo com
                    // um token que nao vale mais.
                    t is HttpException && t.code() == 401 -> {
                        _state.update {
                            it.copy(phase = CallPhase.Idle, errorMessage = null)
                        }
                        onSessionExpired?.invoke()
                    }
                    // 403: a conta e valida, mas a empresa estourou o limite ou
                    // teve o codigo revogado. Nao adianta entrar de novo.
                    t is HttpException && t.code() == 403 ->
                        _state.update {
                            it.copy(phase = CallPhase.Failed, errorMessage = SEM_SALDO)
                        }
                    else -> fail(t, "Nao consegui falar com o servidor.")
                }
                return@launch
            }

            credentials = creds

            try {
                connect(creds)
            } catch (t: Throwable) {
                Log.e(TAG, "falha ao entrar na sala", t)
                fail(t, "Nao consegui entrar na conversa.")
            }
        }
    }

    private suspend fun connect(creds: TokenResponse) {
        val active = room ?: buildRoom().also {
            room = it
            observeEvents(it)
        }

        // Uma tentativa anterior pode ter deixado a sala em CONNECTING ou
        // RECONNECTING. O SDK recusa connect() nesse estado com
        // IllegalStateException, e sem isto o "Tentar de novo" falharia para
        // sempre depois do primeiro timeout.
        if (active.state != Room.State.DISCONNECTED) {
            Log.i(TAG, "sala nao estava desconectada; encerrando antes de reconectar")
            active.disconnect()
        }

        active.connect(creds.livekitUrl, creds.token)
        active.localParticipant.setMicrophoneEnabled(_state.value.micEnabled)

        _state.update {
            it.copy(phase = CallPhase.WaitingAvatar, notice = null, errorMessage = null)
        }
        startTimer()
    }

    private fun buildRoom(): Room = LiveKit.create(
        appContext = getApplication(),
        options = RoomOptions(
            // DESLIGADOS de proposito, e isto e importante.
            //
            // adaptiveStream so assina o video quando ha um renderizador
            // preso a faixa; o audio e assinado na hora. Numa chamada com uma
            // faixa so isso nao economiza nada e cria um atraso medido de
            // ~450 ms entre a voz e a boca - quatro vezes o limite de 100 ms
            // da especificacao. dynacast tem o mesmo efeito de rampa e o
            // mesmo beneficio nulo com um unico assinante.
            adaptiveStream = false,
            dynacast = false,
            audioTrackCaptureDefaults = LocalAudioTrackOptions(
                // Cancelamento de eco e obrigatorio: sem ele o microfone
                // capta a propria voz da IARA saindo do alto-falante e o
                // barge-in dispara sozinho, sem parar.
                echoCancellation = true,
                noiseSuppression = true,
                autoGainControl = true,
                highPassFilter = true,
                typingNoiseDetection = false,
            ),
        ),
        overrides = LiveKitOverrides(
            audioOptions = AudioOptions(
                javaAudioDeviceModuleCustomizer = { builder ->
                    // Prefere o AEC/NS do proprio aparelho quando existe.
                    // Xiaomi e Samsung se comportam de forma diferente aqui;
                    // se um modelo especifico ecoar, e este o ponto de ajuste.
                    builder.setUseHardwareAcousticEchoCanceler(true)
                    builder.setUseHardwareNoiseSuppressor(true)
                },
            ),
        ),
    )

    // -- eventos da sala -----------------------------------------------

    private fun observeEvents(room: Room) {
        eventJob?.cancel()
        eventJob = viewModelScope.launch {
            room.events.collect { event ->
                when (event) {
                    is RoomEvent.Connected -> {
                        reconnectAttempt = 0
                        syncAgentState(room)
                    }

                    is RoomEvent.TrackSubscribed -> {
                        val track = event.track
                        if (track is VideoTrack && _state.value.avatarTrack == null) {
                            // Renderiza apenas a primeira faixa de video
                            // remota. Se o motor de avatar publicar mais de
                            // uma, ou se outro participante entrar, ignoramos.
                            Log.i(TAG, "video do avatar recebido: ${track.sid}")
                            _state.update {
                                it.copy(phase = CallPhase.Active, avatarTrack = track)
                            }
                            avatarIdentity = event.participant.identity?.value
                            // Avisa o agente que ja da para ouvir e ver. Sem
                            // isto ele comeca a falar antes de o app assinar
                            // as faixas, e o comeco da frase se perde.
                            announceReady()
                        }
                    }

                    is RoomEvent.TrackUnsubscribed -> {
                        if (event.track === _state.value.avatarTrack) {
                            _state.update {
                                it.copy(
                                    avatarTrack = null,
                                    // Durante uma reconexao a faixa cai e volta.
                                    // Rebaixar a fase aqui faria a tela dizer
                                    // "Chamando a IARA" por cima do aviso de
                                    // reconexao, contradizendo o proprio aviso.
                                    phase = if (it.phase == CallPhase.Active) {
                                        CallPhase.WaitingAvatar
                                    } else {
                                        it.phase
                                    },
                                )
                            }
                        }
                    }

                    is RoomEvent.ParticipantAttributesChanged -> {
                        readAgentState(event.participant)
                    }

                    is RoomEvent.ActiveSpeakersChanged -> {
                        // "Falando" passa a sair daqui, e nao do atributo
                        // lk.agent.state.
                        //
                        // O agente marca "speaking" quando ENTREGA o audio ao
                        // motor de avatar. Mas o bitHuman ainda precisa
                        // renderizar e transmitir, entao o rotulo acendia
                        // antes de a boca se mexer. Este evento vem da energia
                        // de audio que realmente chegou no aparelho: acende
                        // junto com a voz.
                        val avatarFalando = event.speakers.any {
                            it.identity?.value == avatarIdentity
                        }
                        _state.update {
                            when {
                                avatarFalando -> it.copy(agentState = AgentState.Speaking)
                                // Ao parar de falar, "Pensando" so' continua se
                                // o agente ainda estiver processando.
                                it.agentState == AgentState.Speaking ->
                                    it.copy(agentState = AgentState.Listening)
                                else -> it
                            }
                        }
                    }

                    is RoomEvent.ParticipantConnected -> syncAgentState(room)

                    is RoomEvent.Reconnecting -> {
                        _state.update {
                            it.copy(
                                phase = CallPhase.Reconnecting,
                                notice = "Conexao instavel, reconectando",
                            )
                        }
                    }

                    is RoomEvent.Reconnected -> {
                        reconnectAttempt = 0
                        _state.update {
                            it.copy(
                                phase = if (it.avatarTrack != null) {
                                    CallPhase.Active
                                } else {
                                    CallPhase.WaitingAvatar
                                },
                                notice = null,
                            )
                        }
                    }

                    is RoomEvent.Disconnected -> handleDisconnect()

                    is RoomEvent.FailedToConnect -> {
                        Log.e(TAG, "falha ao conectar", event.error)
                        handleDisconnect()
                    }

                    else -> Unit
                }
            }
        }
    }

    /**
     * Publica um atributo dizendo que o app ja esta recebendo o avatar.
     *
     * O agente espera por este sinal antes da primeira fala. E um handshake,
     * nao um atraso fixo: em rede boa a saudacao sai na hora, em rede ruim
     * ela espera o quanto for preciso em vez de falar para ninguem.
     */
    private fun announceReady() {
        viewModelScope.launch {
            runCatching {
                room?.localParticipant?.updateAttributes(mapOf(APP_READY_ATTRIBUTE to "1"))
            }.onFailure { Log.w(TAG, "nao consegui avisar que o app esta pronto", it) }
        }
    }

    private fun syncAgentState(room: Room) {
        room.remoteParticipants.values.forEach { readAgentState(it) }
    }

    private fun readAgentState(participant: Participant) {
        val raw = participant.attributes[AGENT_STATE_ATTRIBUTE] ?: return
        val parsed = AgentState.from(raw)

        // "Falando" e ignorado aqui de proposito: ele chega antes de o audio
        // sair no aparelho e faria o rotulo acender cedo demais. Quem manda
        // nesse estado e o ActiveSpeakersChanged, que ouve o audio de verdade.
        //
        // "Pensando" vem daqui porque nao tem som nenhum para delatar.
        if (parsed == AgentState.Unknown || parsed == AgentState.Speaking) return

        _state.update {
            // Nao rebaixa "Falando" enquanto o audio ainda estiver saindo.
            if (it.agentState == AgentState.Speaking && parsed == AgentState.Listening) {
                it
            } else {
                it.copy(agentState = parsed)
            }
        }
    }

    // -- reconexao -----------------------------------------------------

    private fun handleDisconnect() {
        if (userInitiatedEnd) {
            finish(EndReason.User)
            return
        }

        val creds = credentials
        if (creds == null || reconnectAttempt >= RECONNECT_BACKOFF.size) {
            finish(if (reconnectAttempt > 0) EndReason.NetworkLost else EndReason.ServerClosed)
            return
        }

        // O SDK ja tem reconexao interna. Este laco cobre o caso em que ela
        // desiste: espacamos as tentativas para nao martelar o servidor nem
        // torrar bateria num tunel sem sinal.
        val wait = RECONNECT_BACKOFF[reconnectAttempt]
        reconnectAttempt += 1
        _state.update {
            it.copy(
                phase = CallPhase.Reconnecting,
                notice = "Sem conexao, tentando de novo",
                avatarTrack = null,
            )
        }

        viewModelScope.launch {
            delay(wait)
            if (userInitiatedEnd) return@launch
            try {
                connect(creds)
            } catch (t: Throwable) {
                Log.w(TAG, "tentativa $reconnectAttempt de reconexao falhou", t)
                handleDisconnect()
            }
        }
    }

    // -- controles -----------------------------------------------------

    fun toggleMute() {
        val next = !_state.value.micEnabled
        _state.update { it.copy(micEnabled = next) }
        viewModelScope.launch {
            runCatching { room?.localParticipant?.setMicrophoneEnabled(next) }
                .onFailure { Log.w(TAG, "nao consegui alterar o microfone", it) }
        }
    }

    fun end() {
        userInitiatedEnd = true
        viewModelScope.launch {
            room?.disconnect()
            finish(EndReason.User)
        }
    }

    /** Traduz a excecao numa frase que faz sentido para quem esta na tela. */
    private fun fail(t: Throwable, fallback: String) {
        val friendly = when (t) {
            is java.net.SocketTimeoutException ->
                "O servidor demorou demais para responder."
            is java.net.UnknownHostException ->
                "Nao encontrei o servidor. Confira a conexao."
            is java.net.ConnectException ->
                "O servidor nao respondeu. Ele esta no ar?"
            is java.io.IOException ->
                "Falha de rede. Tente de novo."
            else -> fallback
        }
        _state.update { it.copy(phase = CallPhase.Failed, errorMessage = friendly) }
    }

    private fun finish(reason: EndReason) {
        timerJob?.cancel()
        timerJob = null
        _state.update {
            it.copy(
                phase = CallPhase.Ended,
                endReason = reason,
                avatarTrack = null,
                notice = null,
                agentState = AgentState.Unknown,
            )
        }
    }

    fun reset() {
        avatarIdentity = null
        userInitiatedEnd = true
        reconnectAttempt = 0
        credentials = null
        // Solta a sala da tentativa anterior. Sem isto o proximo start()
        // encontraria um Room em estado sujo.
        room?.let { if (it.state != Room.State.DISCONNECTED) it.disconnect() }
        _state.value = CallUiState()
    }

    private fun startTimer() {
        if (timerJob != null) return
        timerJob = viewModelScope.launch {
            while (true) {
                delay(1_000)
                _state.update { it.copy(elapsedSeconds = it.elapsedSeconds + 1) }
            }
        }
    }

    // -- renderizacao --------------------------------------------------

    /** Prepara um renderer para esta sala. Necessario antes de anexar a faixa. */
    fun initRenderer(renderer: TextureViewRenderer) {
        room?.initVideoRenderer(renderer)
    }

    // -- limpeza -------------------------------------------------------

    override fun onCleared() {
        super.onCleared()
        timerJob?.cancel()
        eventJob?.cancel()
        // release() devolve o microfone e derruba a PeerConnection. Sem isto,
        // o indicador de microfone do sistema fica aceso depois de sair.
        room?.release()
        room = null
    }
}
