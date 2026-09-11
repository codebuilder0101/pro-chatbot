package br.com.iara.chat.data

import br.com.iara.chat.BuildConfig
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import retrofit2.http.Body
import retrofit2.http.POST
import java.util.concurrent.TimeUnit

@Serializable
data class TokenRequest(
    @SerialName("user_id") val userId: String,
    @SerialName("display_name") val displayName: String = "",
)

@Serializable
data class TokenResponse(
    @SerialName("livekit_url") val livekitUrl: String,
    @SerialName("token") val token: String,
    @SerialName("room") val room: String,
    @SerialName("expires_in_s") val expiresInS: Int = 0,
)

interface TokenApi {
    @POST("token")
    suspend fun createToken(@Body request: TokenRequest): TokenResponse
}

object TokenApiFactory {

    private val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
    }

    fun create(): TokenApi {
        val auth = Interceptor { chain ->
            // Este e o unico segredo que o APK carrega, e ele nao abre nada
            // alem de um pedido de token de sala. As chaves de ElevenLabs,
            // HeyGen, Deepgram e LLM nunca chegam ao dispositivo.
            val request = chain.request().newBuilder()
                .addHeader("x-api-key", BuildConfig.TOKEN_SERVER_KEY)
                .build()
            chain.proceed(request)
        }

        val clientBuilder = OkHttpClient.Builder()
            .addInterceptor(auth)
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(20, TimeUnit.SECONDS)

        if (BuildConfig.DEBUG) {
            clientBuilder.addInterceptor(
                HttpLoggingInterceptor().apply {
                    // BASIC, nao BODY: o corpo da resposta contem o token.
                    level = HttpLoggingInterceptor.Level.BASIC
                },
            )
        }

        return Retrofit.Builder()
            .baseUrl(BuildConfig.TOKEN_SERVER_URL)
            .client(clientBuilder.build())
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(TokenApi::class.java)
    }
}
