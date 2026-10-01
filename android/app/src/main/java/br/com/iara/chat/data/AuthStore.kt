package br.com.iara.chat.data

import android.content.Context
import android.content.SharedPreferences

/**
 * Guarda a sessao de quem entrou.
 *
 * O que fica no aparelho e um token opaco de sessao, nunca a senha. O servidor
 * guarda so o hash desse token, entao nem o banco dele devolve acesso se
 * vazar. A senha nao e salva em lugar nenhum do app.
 *
 * Sessao dura 30 dias por padrao; depois disso o servidor responde 401 e o app
 * devolve a pessoa para a tela de entrada.
 */
class AuthStore(context: Context) {

    private val prefs: SharedPreferences =
        context.applicationContext.getSharedPreferences(ARQUIVO, Context.MODE_PRIVATE)

    val sessionToken: String?
        get() = prefs.getString(TOKEN, null)?.takeIf { it.isNotBlank() }

    val email: String
        get() = prefs.getString(EMAIL, "").orEmpty()

    val nome: String
        get() = prefs.getString(NOME, "").orEmpty()

    val isLoggedIn: Boolean
        get() = sessionToken != null

    fun save(token: String, email: String, nome: String) {
        prefs.edit()
            .putString(TOKEN, token)
            .putString(EMAIL, email)
            .putString(NOME, nome)
            .apply()
    }

    /** Usado no logout e quando o servidor recusa a sessao. */
    fun clear() {
        prefs.edit().remove(TOKEN).remove(NOME).apply()
        // O email continua guardado de proposito: na proxima entrada ele ja
        // vem preenchido, que e o comportamento que as pessoas esperam.
    }

    companion object {
        private const val ARQUIVO = "iara_conta"
        private const val TOKEN = "session_token"
        private const val EMAIL = "email"
        private const val NOME = "nome"

        const val SENHA_MINIMA = 8

        fun emailParece(valido: String): Boolean =
            valido.contains("@") && valido.substringAfter("@").contains(".") &&
                !valido.contains(" ") && valido.length >= 5

        fun senhaParece(senha: String): Boolean = senha.length >= SENHA_MINIMA
    }
}
