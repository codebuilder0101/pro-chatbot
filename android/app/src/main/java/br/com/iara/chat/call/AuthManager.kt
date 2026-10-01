package br.com.iara.chat.call

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import br.com.iara.chat.data.AuthStore
import br.com.iara.chat.data.CadastroRequest
import br.com.iara.chat.data.EntrarRequest
import br.com.iara.chat.data.TokenApiFactory
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import retrofit2.HttpException

/** Em que tela de conta estamos. */
enum class AuthScreen { Entrar, Cadastrar }

data class AuthUiState(
    val screen: AuthScreen = AuthScreen.Entrar,
    val loading: Boolean = false,
    val errorMessage: String? = null,
    val loggedIn: Boolean = false,
    val nome: String = "",
    val emailLembrado: String = "",
)

/**
 * Cadastro e entrada.
 *
 * A senha nunca e guardada no aparelho: o que fica e um token de sessao que o
 * servidor pode revogar. Quando o servidor responde 401, o token morreu e a
 * pessoa volta para a tela de entrada.
 */
class AuthManager(application: Application) : AndroidViewModel(application) {

    private companion object {
        const val TAG = "AuthManager"
        const val ERRO_REDE = "Nao consegui falar com o servidor. Confira a conexao."
    }

    private val api = TokenApiFactory.createAuth()
    val store = AuthStore(application)

    private val json = Json { ignoreUnknownKeys = true }

    private val _state = MutableStateFlow(
        AuthUiState(loggedIn = store.isLoggedIn, nome = store.nome, emailLembrado = store.email),
    )
    val state: StateFlow<AuthUiState> = _state.asStateFlow()

    fun mostrar(screen: AuthScreen) {
        _state.update { it.copy(screen = screen, errorMessage = null) }
    }

    fun limparErro() {
        _state.update { it.copy(errorMessage = null) }
    }

    fun entrar(email: String, senha: String) {
        if (_state.value.loading) return
        _state.update { it.copy(loading = true, errorMessage = null) }
        viewModelScope.launch {
            try {
                val s = api.entrar(EntrarRequest(email = email.trim(), senha = senha))
                store.save(s.sessionToken, s.email, s.nome)
                _state.update {
                    it.copy(loading = false, loggedIn = true, nome = s.nome, emailLembrado = s.email)
                }
            } catch (t: Throwable) {
                Log.e(TAG, "falha ao entrar", t)
                _state.update { it.copy(loading = false, errorMessage = mensagemDe(t)) }
            }
        }
    }

    fun cadastrar(nome: String, email: String, senha: String, codigo: String) {
        if (_state.value.loading) return
        _state.update { it.copy(loading = true, errorMessage = null) }
        viewModelScope.launch {
            try {
                val s = api.registrar(
                    CadastroRequest(
                        email = email.trim(),
                        senha = senha,
                        nome = nome.trim(),
                        accessCode = codigo,
                    ),
                )
                store.save(s.sessionToken, s.email, s.nome)
                _state.update {
                    it.copy(loading = false, loggedIn = true, nome = s.nome, emailLembrado = s.email)
                }
            } catch (t: Throwable) {
                Log.e(TAG, "falha ao cadastrar", t)
                _state.update { it.copy(loading = false, errorMessage = mensagemDe(t)) }
            }
        }
    }

    fun sair() {
        val token = store.sessionToken
        store.clear()
        _state.update {
            it.copy(loggedIn = false, screen = AuthScreen.Entrar, errorMessage = null, nome = "")
        }
        // Avisa o servidor para apagar a sessao, mas sem segurar a interface:
        // o aparelho ja esqueceu o token de qualquer jeito.
        if (token != null) {
            viewModelScope.launch {
                runCatching { api.sair("Bearer $token") }
                    .onFailure { Log.w(TAG, "logout remoto falhou", it) }
            }
        }
    }

    /** Chamado quando o /token responde 401: a sessao morreu no servidor. */
    fun sessaoExpirou() {
        store.clear()
        _state.update {
            it.copy(
                loggedIn = false,
                screen = AuthScreen.Entrar,
                errorMessage = "Sua sessao expirou. Entre de novo.",
            )
        }
    }

    /**
     * O servidor manda a explicacao no corpo, em `detail`. Mostrar ela e
     * melhor do que inventar texto aqui: "senha curta" e "email ja existe"
     * sao coisas que a pessoa resolve, e so o servidor sabe qual aconteceu.
     */
    private fun mensagemDe(t: Throwable): String {
        if (t !is HttpException) return ERRO_REDE
        val corpo = runCatching { t.response()?.errorBody()?.string() }.getOrNull()
        val detalhe = corpo?.let {
            runCatching { json.decodeFromString<Map<String, String>>(it)["detail"] }.getOrNull()
        }
        return detalhe?.takeIf { it.isNotBlank() } ?: when (t.code()) {
            401 -> "Email ou senha incorretos."
            403 -> "Codigo de acesso invalido."
            409 -> "Ja existe uma conta com esse email."
            503 -> "Cadastro indisponivel no momento. Tente mais tarde."
            else -> ERRO_REDE
        }
    }
}
