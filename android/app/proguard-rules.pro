# LiveKit carrega classes nativas do WebRTC por reflexao; sem isto o R8 corta
# o que o SDK procura em runtime e a chamada cai sem erro claro.
-keep class org.webrtc.** { *; }
-keep class livekit.** { *; }
-keep class io.livekit.android.** { *; }

# kotlinx.serialization gera serializers estaticos.
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.**
-keepclassmembers class br.com.iara.chat.data.** {
    *** Companion;
}
-keepclasseswithmembers class br.com.iara.chat.data.** {
    kotlinx.serialization.KSerializer serializer(...);
}

# Retrofit/OkHttp
-dontwarn okhttp3.**
-dontwarn okio.**
-dontwarn retrofit2.**
-keepattributes Signature, Exceptions
