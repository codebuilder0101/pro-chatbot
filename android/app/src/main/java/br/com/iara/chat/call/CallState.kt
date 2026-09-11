package br.com.iara.chat.call

import io.livekit.android.room.track.VideoTrack

/** Em que ponto da chamada estamos. */
enum class CallPhase {
    /** Nada aconteceu ainda. */
    Idle,

    /** Pedindo token e abrindo a sala. */
    Connecting,

    /** Na sala, mas o avatar ainda nao publicou video. */
    WaitingAvatar,

    /** Video na tela, conversa rolando. */
    Active,

    /** Perdemos a rede; o SDK esta tentando voltar. */
    Reconnecting,

    /** Acabou. Ver [CallUiState.endReason]. */
    Ended,

    /** Falhou antes de comecar. Ver [CallUiState.errorMessage]. */
    Failed,
}

/**
 * O que a IARA esta fazendo agora.
 *
 * Vem do atributo `lk.agent.state`, que o LiveKit Agents publica no
 * participante do agente. Nao inferimos pelo audio: quando ha avatar, quem
 * publica o audio e o motor de renderizacao, e o estado ficaria atrasado.
 */
enum class AgentState {
    Unknown,
    Initializing,
    Listening,
    Thinking,
    Speaking,
    ;

    companion object {
        fun from(raw: String?): AgentState = when (raw?.lowercase()) {
            "initializing" -> Initializing
            "listening" -> Listening
            "thinking" -> Thinking
            "speaking" -> Speaking
            else -> Unknown
        }
    }
}

enum class EndReason {
    User,
    ServerClosed,
    NetworkLost,
}

data class CallUiState(
    val phase: CallPhase = CallPhase.Idle,
    val agentState: AgentState = AgentState.Unknown,
    val micEnabled: Boolean = true,
    val avatarTrack: VideoTrack? = null,
    val endReason: EndReason? = null,
    val errorMessage: String? = null,
    /** Aviso discreto que nao derruba a sessao, ex.: reconectando. */
    val notice: String? = null,
    val elapsedSeconds: Int = 0,
)
