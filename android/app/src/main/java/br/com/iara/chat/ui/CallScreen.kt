package br.com.iara.chat.ui

import androidx.compose.foundation.Image
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CallEnd
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.com.iara.chat.R
import br.com.iara.chat.call.AgentState
import br.com.iara.chat.call.CallPhase
import br.com.iara.chat.call.CallUiState
import br.com.iara.chat.ui.theme.Coral
import br.com.iara.chat.ui.theme.Ink
import br.com.iara.chat.ui.theme.InkElevated
import br.com.iara.chat.ui.theme.Lilac
import br.com.iara.chat.ui.theme.LilacBright
import br.com.iara.chat.ui.theme.LilacDeep
import br.com.iara.chat.ui.theme.MistDim
import io.livekit.android.renderer.TextureViewRenderer

@Composable
fun CallScreen(
    state: CallUiState,
    onToggleMute: () -> Unit,
    onEnd: () -> Unit,
    initRenderer: (TextureViewRenderer) -> Unit,
) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    listOf(Color(0xFF2A1F4A), Ink),
                ),
            ),
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 24.dp, vertical = 32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.SpaceBetween,
        ) {
            TopBar(state)

            AvatarStage(state, initRenderer)

            Controls(
                micEnabled = state.micEnabled,
                onToggleMute = onToggleMute,
                onEnd = onEnd,
            )
        }
    }
}

@Composable
private fun TopBar(state: CallUiState) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = "IARA",
            color = Lilac,
            fontSize = 15.sp,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(Modifier.height(4.dp))
        Text(
            text = formatElapsed(state.elapsedSeconds),
            color = MistDim,
            fontSize = 13.sp,
        )

        AnimatedVisibility(visible = state.notice != null) {
            Surface(
                shape = RoundedCornerShape(999.dp),
                color = InkElevated,
                modifier = Modifier.padding(top = 10.dp),
            ) {
                Text(
                    text = state.notice.orEmpty(),
                    color = MistDim,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 6.dp),
                )
            }
        }
    }
}

@Composable
private fun AvatarStage(
    state: CallUiState,
    initRenderer: (TextureViewRenderer) -> Unit,
) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Box(
            modifier = Modifier
                .fillMaxWidth(0.82f)
                .aspectRatio(1f),
            contentAlignment = Alignment.Center,
        ) {
            // Halo que pulsa enquanto ela fala. E o unico movimento da tela,
            // entao ele carrega sozinho a sensacao de "ela esta ativa".
            SpeakingHalo(active = state.agentState == AgentState.Speaking)

            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .clip(CircleShape)
                    .background(Lilac.copy(alpha = 0.18f))
                    .border(2.dp, LilacBright.copy(alpha = 0.55f), CircleShape),
                contentAlignment = Alignment.Center,
            ) {
                val track = state.avatarTrack
                if (track != null) {
                    AvatarVideo(
                        track = track,
                        initRenderer = initRenderer,
                        modifier = Modifier
                            .fillMaxSize()
                            .clip(CircleShape),
                    )
                } else {
                    // Enquanto o motor de avatar nao publica video, mostramos a
                    // foto da IARA em vez de um circulo vazio. E' imagem parada:
                    // o rosto que fala vem da faixa de video, nao daqui.
                    Image(
                        painter = painterResource(R.drawable.iara_avatar),
                        contentDescription = null,
                        contentScale = ContentScale.Crop,
                        modifier = Modifier
                            .fillMaxSize()
                            .clip(CircleShape),
                    )
                    CircularProgressIndicator(
                        color = Color.White,
                        strokeWidth = 2.dp,
                        modifier = Modifier
                            .align(Alignment.BottomCenter)
                            .padding(bottom = 34.dp)
                            .size(26.dp),
                    )
                }
            }
        }

        Spacer(Modifier.height(28.dp))

        Text(
            text = stringResource(statusLabel(state)),
            color = MistDim,
            style = MaterialTheme.typography.titleMedium,
        )
    }
}

@Composable
private fun SpeakingHalo(active: Boolean) {
    val transition = rememberInfiniteTransition(label = "halo")
    val scale by transition.animateFloat(
        initialValue = 1f,
        targetValue = 1.06f,
        animationSpec = infiniteRepeatable(
            animation = tween(900),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "halo-scale",
    )

    Box(
        modifier = Modifier
            .fillMaxSize()
            .alpha(if (active) 0.35f else 0f)
            .clip(CircleShape)
            .background(
                Brush.radialGradient(
                    listOf(LilacBright.copy(alpha = scale - 0.6f), Color.Transparent),
                ),
            ),
    )
}

@Composable
private fun Controls(
    micEnabled: Boolean,
    onToggleMute: () -> Unit,
    onEnd: () -> Unit,
) {
    Row(
        horizontalArrangement = Arrangement.spacedBy(28.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        RoundButton(
            onClick = onToggleMute,
            background = if (micEnabled) InkElevated else LilacDeep,
        ) {
            Icon(
                imageVector = if (micEnabled) Icons.Filled.Mic else Icons.Filled.MicOff,
                contentDescription = stringResource(
                    if (micEnabled) R.string.call_mute else R.string.call_unmute,
                ),
                tint = Color.White,
            )
        }

        RoundButton(onClick = onEnd, background = Coral, size = 68) {
            Icon(
                imageVector = Icons.Filled.CallEnd,
                contentDescription = stringResource(R.string.call_end),
                tint = Color.White,
            )
        }
    }
}

@Composable
private fun RoundButton(
    onClick: () -> Unit,
    background: Color,
    size: Int = 58,
    content: @Composable () -> Unit,
) {
    Box(
        modifier = Modifier
            .size(size.dp)
            .clip(CircleShape)
            .background(background)
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        content()
    }
}

private fun statusLabel(state: CallUiState): Int = when {
    state.phase == CallPhase.Connecting -> R.string.state_connecting
    state.phase == CallPhase.Reconnecting -> R.string.state_reconnecting
    state.phase == CallPhase.WaitingAvatar -> R.string.state_waiting_avatar
    state.agentState == AgentState.Thinking -> R.string.state_thinking
    state.agentState == AgentState.Speaking -> R.string.state_speaking
    else -> R.string.state_listening
}

private fun formatElapsed(seconds: Int): String {
    val m = seconds / 60
    val s = seconds % 60
    return "%02d:%02d".format(m, s)
}
