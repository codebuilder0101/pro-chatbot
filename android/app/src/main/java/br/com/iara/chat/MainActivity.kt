package br.com.iara.chat

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import androidx.core.view.WindowCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import br.com.iara.chat.call.CallForegroundService
import br.com.iara.chat.call.CallPhase
import br.com.iara.chat.call.RoomManager
import br.com.iara.chat.call.AuthManager
import br.com.iara.chat.call.AuthScreen
import br.com.iara.chat.ui.CallScreen
import br.com.iara.chat.ui.LoginScreen
import br.com.iara.chat.ui.RegisterScreen
import br.com.iara.chat.ui.EndScreen
import br.com.iara.chat.ui.HomeScreen
import br.com.iara.chat.ui.theme.IaraTheme

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, true)

        setContent {
            IaraTheme {
                IaraRoot()
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        // Rede de seguranca: se a Activity morrer com a chamada aberta, o
        // servico nao pode sobreviver segurando o microfone.
        CallForegroundService.stop(this)
    }
}

@Composable
private fun IaraRoot(
    manager: RoomManager = viewModel(),
    auth: AuthManager = viewModel(),
) {
    val context = LocalContext.current
    val state by manager.state.collectAsStateWithLifecycle()
    val authState by auth.state.collectAsStateWithLifecycle()

    var permissionDenied by remember { mutableStateOf(false) }
    var pendingStart by remember { mutableStateOf(false) }


    val micLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        permissionDenied = !granted
        if (granted && pendingStart) {
            pendingStart = false
            manager.start()
        }
    }

    val notificationLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { /* negar a notificacao nao impede a chamada, so a torna menos visivel */ }

    // O foreground service acompanha o estado da chamada em vez de ser ligado
    // e desligado a mao em cada botao: um caminho de saida esquecido deixaria
    // o microfone aberto com a notificacao no lugar.
    LaunchedEffect(state.phase) {
        when (state.phase) {
            CallPhase.Connecting,
            CallPhase.WaitingAvatar,
            CallPhase.Active,
            CallPhase.Reconnecting,
            -> CallForegroundService.start(context)

            else -> CallForegroundService.stop(context)
        }
    }

    // Quando o /token responde 401 a sessao morreu no servidor. O RoomManager
    // avisa por aqui e a pessoa volta para a tela de entrada.
    //
    // Precisa ser efeito, e nao chamada no corpo do composable: mexer em
    // estado durante a composicao realimenta a propria composicao.
    LaunchedEffect(Unit) {
        manager.onSessionExpired = { auth.sessaoExpirou() }
    }

    if (!authState.loggedIn) {
        when (authState.screen) {
            AuthScreen.Entrar -> LoginScreen(
                emailInicial = authState.emailLembrado,
                carregando = authState.loading,
                errorMessage = authState.errorMessage,
                onEntrar = auth::entrar,
                onIrParaCadastro = { auth.mostrar(AuthScreen.Cadastrar) },
            )

            AuthScreen.Cadastrar -> RegisterScreen(
                carregando = authState.loading,
                errorMessage = authState.errorMessage,
                onCadastrar = auth::cadastrar,
                onIrParaEntrar = { auth.mostrar(AuthScreen.Entrar) },
            )
        }
        return
    }

    when (state.phase) {
        CallPhase.Idle -> HomeScreen(
            nome = authState.nome,
            // Mostra qual motor este APK usa. Sem isto, com os dois
            // instalados lado a lado, nao da para saber qual esta aberto.
            motorAvatar = BuildConfig.AVATAR_ENGINE,
            onSair = {
                manager.reset()
                auth.sair()
            },
            permissionDenied = permissionDenied,
            onOpenSettings = {
                context.startActivity(
                    Intent(
                        Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                        Uri.fromParts("package", context.packageName, null),
                    ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                )
            },
            onStart = {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
                    ContextCompat.checkSelfPermission(
                        context,
                        Manifest.permission.POST_NOTIFICATIONS,
                    ) != PackageManager.PERMISSION_GRANTED
                ) {
                    notificationLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                }

                val hasMic = ContextCompat.checkSelfPermission(
                    context,
                    Manifest.permission.RECORD_AUDIO,
                ) == PackageManager.PERMISSION_GRANTED

                if (hasMic) {
                    permissionDenied = false
                    manager.start()
                } else {
                    pendingStart = true
                    micLauncher.launch(Manifest.permission.RECORD_AUDIO)
                }
            },
        )

        CallPhase.Ended, CallPhase.Failed -> EndScreen(
            reason = state.endReason,
            errorMessage = state.errorMessage,
            onRestart = { manager.reset() },
        )

        else -> CallScreen(
            state = state,
            onToggleMute = manager::toggleMute,
            onEnd = manager::end,
            initRenderer = manager::initRenderer,
        )
    }
}
