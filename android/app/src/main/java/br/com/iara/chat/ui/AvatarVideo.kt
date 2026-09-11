package br.com.iara.chat.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import io.livekit.android.renderer.TextureViewRenderer
import io.livekit.android.room.track.VideoTrack
import livekit.org.webrtc.RendererCommon

/**
 * Desenha a faixa de video do avatar.
 *
 * Usa TextureViewRenderer, e nao SurfaceViewRenderer, porque o recorte
 * circular da referencia visual exige que a View aceite clip e alpha vindos
 * do Compose. SurfaceView desenha numa camada propria e o recorte nao pega.
 */
@Composable
fun AvatarVideo(
    track: VideoTrack,
    initRenderer: (TextureViewRenderer) -> Unit,
    modifier: Modifier = Modifier,
) {
    var renderer by remember { mutableStateOf<TextureViewRenderer?>(null) }

    AndroidView(
        modifier = modifier,
        factory = { context ->
            TextureViewRenderer(context).also { view ->
                // initVideoRenderer da sala precisa vir antes de qualquer
                // frame; e ele que entrega o contexto EGL compartilhado.
                initRenderer(view)
                view.setScalingType(RendererCommon.ScalingType.SCALE_ASPECT_FILL)
                renderer = view
            }
        },
        onRelease = { view ->
            renderer = null
            view.release()
        },
    )

    // A ligacao acompanha a troca de faixa. Sem reagir a `track`, o renderer
    // fica preso na faixa antiga depois de uma reconexao e a tela congela no
    // ultimo frame recebido.
    DisposableEffect(track, renderer) {
        val current = renderer
        current?.let { track.addRenderer(it) }
        onDispose { current?.let { track.removeRenderer(it) } }
    }
}
