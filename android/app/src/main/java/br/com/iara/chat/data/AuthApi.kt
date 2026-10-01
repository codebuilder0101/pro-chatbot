package br.com.iara.chat.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import retrofit2.http.Body
import retrofit2.http.Header
import retrofit2.http.POST

@Serializable
data class CadastroRequest(
    val email: String,
    val senha: String,
    val nome: String = "",
    /** Diz de qual empresa a pessoa e. Exigido pelo servidor no cadastro. */
    @SerialName("access_code") val accessCode: String = "",
)

@Serializable
data class EntrarRequest(
    val email: String,
    val senha: String,
)

@Serializable
data class SessaoResponse(
    @SerialName("session_token") val sessionToken: String,
    val email: String = "",
    val nome: String = "",
    @SerialName("expires_at") val expiresAt: String = "",
)

/** Mensagem de erro que o servidor manda no corpo das recusas. */
@Serializable
data class ErroResponse(val detail: String = "")

interface AuthApi {
    @POST("auth/register")
    suspend fun registrar(@Body request: CadastroRequest): SessaoResponse

    @POST("auth/login")
    suspend fun entrar(@Body request: EntrarRequest): SessaoResponse

    @POST("auth/logout")
    suspend fun sair(@Header("Authorization") authorization: String): Map<String, Boolean>
}
