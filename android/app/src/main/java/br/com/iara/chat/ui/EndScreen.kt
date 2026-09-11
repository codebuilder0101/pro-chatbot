package br.com.iara.chat.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import br.com.iara.chat.R
import br.com.iara.chat.call.EndReason
import br.com.iara.chat.ui.theme.Ink
import br.com.iara.chat.ui.theme.LilacBright
import br.com.iara.chat.ui.theme.Mist
import br.com.iara.chat.ui.theme.MistDim

@Composable
fun EndScreen(
    reason: EndReason?,
    errorMessage: String?,
    onRestart: () -> Unit,
) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Brush.verticalGradient(listOf(Color(0xFF2A1F4A), Ink)))
            .padding(32.dp),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Text(
                text = stringResource(
                    if (errorMessage != null) R.string.error_title else R.string.end_title,
                ),
                color = Mist,
                style = MaterialTheme.typography.headlineSmall,
                textAlign = TextAlign.Center,
            )

            Spacer(Modifier.height(10.dp))

            Text(
                text = errorMessage ?: stringResource(reasonLabel(reason)),
                color = MistDim,
                style = MaterialTheme.typography.bodyMedium,
                textAlign = TextAlign.Center,
            )

            Spacer(Modifier.height(40.dp))

            Button(
                onClick = onRestart,
                shape = RoundedCornerShape(999.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = LilacBright,
                    contentColor = Ink,
                ),
                modifier = Modifier
                    .fillMaxWidth()
                    .height(54.dp),
            ) {
                Text(
                    text = stringResource(
                        if (errorMessage != null) R.string.error_retry else R.string.end_again,
                    ),
                    style = MaterialTheme.typography.labelLarge,
                )
            }
        }
    }
}

private fun reasonLabel(reason: EndReason?): Int = when (reason) {
    EndReason.NetworkLost -> R.string.end_reason_network
    EndReason.ServerClosed -> R.string.end_reason_time
    else -> R.string.end_reason_user
}
