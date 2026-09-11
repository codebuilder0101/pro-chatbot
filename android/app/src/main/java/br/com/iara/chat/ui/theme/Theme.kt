package br.com.iara.chat.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

// Paleta tirada da referencia visual do cliente: fundo lilas, avatar em
// recorte circular. O app fica escuro para o video nao competir com a UI.
val Lilac = Color(0xFFC9B6F0)
val LilacBright = Color(0xFFA98CF0)
val LilacDeep = Color(0xFF6E4FBF)
val Ink = Color(0xFF171029)
val InkSurface = Color(0xFF221839)
val InkElevated = Color(0xFF2E2249)
val Coral = Color(0xFFE86A6A)
val Mist = Color(0xFFEDE7FA)
val MistDim = Color(0xFFB6ADC9)

private val IaraColors = darkColorScheme(
    primary = LilacBright,
    onPrimary = Ink,
    primaryContainer = LilacDeep,
    onPrimaryContainer = Mist,
    secondary = Lilac,
    onSecondary = Ink,
    background = Ink,
    onBackground = Mist,
    surface = InkSurface,
    onSurface = Mist,
    surfaceVariant = InkElevated,
    onSurfaceVariant = MistDim,
    error = Coral,
    onError = Ink,
)

private val IaraTypography = Typography(
    displaySmall = TextStyle(fontSize = 30.sp, fontWeight = FontWeight.SemiBold),
    headlineSmall = TextStyle(fontSize = 22.sp, fontWeight = FontWeight.SemiBold),
    titleMedium = TextStyle(fontSize = 17.sp, fontWeight = FontWeight.Medium),
    bodyLarge = TextStyle(fontSize = 16.sp, lineHeight = 24.sp),
    bodyMedium = TextStyle(fontSize = 14.sp, lineHeight = 20.sp),
    labelLarge = TextStyle(fontSize = 15.sp, fontWeight = FontWeight.Medium),
)

@Composable
fun IaraTheme(
    @Suppress("UNUSED_PARAMETER") darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    // Tema unico, escuro. Uma chamada de video nao deveria mudar de cor
    // porque o telefone entrou no modo claro.
    MaterialTheme(
        colorScheme = IaraColors,
        typography = IaraTypography,
        content = content,
    )
}
