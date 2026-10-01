package br.com.iara.chat.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.border
import androidx.compose.material3.Surface
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.com.iara.chat.R
import br.com.iara.chat.ui.theme.Ink
import br.com.iara.chat.ui.theme.Lilac
import br.com.iara.chat.ui.theme.LilacBright
import br.com.iara.chat.ui.theme.LilacDeep
import br.com.iara.chat.ui.theme.Mist
import br.com.iara.chat.ui.theme.MistDim

@Composable
fun HomeScreen(
    onStart: () -> Unit,
    permissionDenied: Boolean,
    onOpenSettings: () -> Unit,
    nome: String = "",
    onSair: () -> Unit = {},
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
            // O rosto da IARA parado, so' para dar cara ao app. Quem fala e'
            // o video que o motor de avatar publica na chamada.
            Image(
                painter = painterResource(R.drawable.iara_avatar),
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = Modifier
                    .size(148.dp)
                    .clip(CircleShape)
                    .background(Lilac.copy(alpha = 0.18f))
                    .border(2.dp, LilacBright.copy(alpha = 0.5f), CircleShape),
            )

            Spacer(Modifier.height(28.dp))

            // A logo e' roxo escuro sobre fundo escuro. O cartao claro atras
            // dela resolve o contraste sem repintar a marca do cliente.
            Surface(
                shape = RoundedCornerShape(18.dp),
                color = Mist,
            ) {
                Image(
                    painter = painterResource(R.drawable.iara_logo),
                    contentDescription = stringResource(R.string.app_name),
                    modifier = Modifier
                        .padding(horizontal = 18.dp, vertical = 12.dp)
                        .fillMaxWidth(0.78f),
                )
            }

            Spacer(Modifier.height(14.dp))
            Text(
                text = stringResource(R.string.home_tagline),
                color = Lilac,
                style = MaterialTheme.typography.bodyLarge,
            )

            Spacer(Modifier.height(48.dp))

            Button(
                onClick = onStart,
                shape = RoundedCornerShape(999.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = LilacBright,
                    contentColor = Ink,
                ),
                modifier = Modifier
                    .fillMaxWidth()
                    .height(56.dp),
            ) {
                Text(
                    text = stringResource(R.string.home_start),
                    style = MaterialTheme.typography.labelLarge,
                )
            }

            Spacer(Modifier.height(18.dp))

            Text(
                text = stringResource(
                    if (permissionDenied) R.string.perm_body else R.string.home_hint,
                ),
                color = MistDim,
                textAlign = TextAlign.Center,
                style = MaterialTheme.typography.bodyMedium,
            )

            if (permissionDenied) {
                TextButton(onClick = onOpenSettings) {
                    Text(
                        text = stringResource(R.string.perm_settings),
                        color = LilacBright,
                    )
                }
            }

            if (nome.isNotBlank()) {
                Text(
                    text = "Conectada como $nome",
                    color = MistDim,
                    textAlign = TextAlign.Center,
                    style = MaterialTheme.typography.bodySmall,
                )
            }

            TextButton(onClick = onSair) {
                Text(text = "Sair da conta", color = MistDim)
            }
        }
    }
}
