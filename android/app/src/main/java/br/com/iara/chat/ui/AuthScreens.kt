package br.com.iara.chat.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.com.iara.chat.R
import br.com.iara.chat.data.AuthStore
import br.com.iara.chat.ui.theme.Coral
import br.com.iara.chat.ui.theme.Ink
import br.com.iara.chat.ui.theme.LilacBright
import br.com.iara.chat.ui.theme.Mist
import br.com.iara.chat.ui.theme.MistDim

@Composable
private fun Cabecalho(subtitulo: String) {
    Image(
        painter = painterResource(R.drawable.iara_avatar),
        contentDescription = null,
        contentScale = ContentScale.Crop,
        modifier = Modifier.size(104.dp).clip(CircleShape),
    )
    Text(
        text = "IARA",
        color = LilacBright,
        fontSize = 28.sp,
        fontWeight = FontWeight.SemiBold,
        modifier = Modifier.padding(top = 16.dp),
    )
    Text(
        text = subtitulo,
        color = Mist,
        fontSize = 14.sp,
        textAlign = TextAlign.Center,
        modifier = Modifier.padding(top = 8.dp, start = 8.dp, end = 8.dp),
    )
}

@Composable
private fun Erro(mensagem: String?) {
    if (mensagem == null) return
    Text(
        text = mensagem,
        color = Coral,
        fontSize = 13.sp,
        textAlign = TextAlign.Center,
        modifier = Modifier.padding(top = 12.dp),
    )
}

@Composable
private fun BotaoPrincipal(
    texto: String,
    habilitado: Boolean,
    carregando: Boolean,
    onClick: () -> Unit,
) {
    Button(
        onClick = onClick,
        enabled = habilitado && !carregando,
        colors = ButtonDefaults.buttonColors(containerColor = LilacBright, contentColor = Ink),
        modifier = Modifier.fillMaxWidth().padding(top = 20.dp),
    ) {
        if (carregando) {
            CircularProgressIndicator(
                color = Ink,
                strokeWidth = 2.dp,
                modifier = Modifier.size(20.dp).padding(vertical = 2.dp),
            )
        } else {
            Text(texto, fontSize = 16.sp, modifier = Modifier.padding(vertical = 6.dp))
        }
    }
}

/** Entrada: email e senha conferidos contra o banco do servidor. */
@Composable
fun LoginScreen(
    emailInicial: String,
    carregando: Boolean,
    errorMessage: String?,
    onEntrar: (String, String) -> Unit,
    onIrParaCadastro: () -> Unit,
) {
    var email by remember { mutableStateOf(emailInicial) }
    var senha by remember { mutableStateOf("") }
    val valido = AuthStore.emailParece(email) && senha.isNotEmpty()

    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 28.dp, vertical = 48.dp),
    ) {
        Cabecalho("Entre com a sua conta para conversar.")

        OutlinedTextField(
            value = email,
            onValueChange = { email = it.trim() },
            singleLine = true,
            label = { Text("Email") },
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.Email,
                imeAction = ImeAction.Next,
            ),
            modifier = Modifier.fillMaxWidth().padding(top = 26.dp),
        )

        OutlinedTextField(
            value = senha,
            onValueChange = { senha = it },
            singleLine = true,
            label = { Text("Senha") },
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.Password,
                imeAction = ImeAction.Done,
            ),
            modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
        )

        Erro(errorMessage)

        BotaoPrincipal("Entrar", valido, carregando) { onEntrar(email, senha) }

        TextButton(onClick = onIrParaCadastro, modifier = Modifier.padding(top = 10.dp)) {
            Text("Nao tenho conta. Quero me cadastrar", color = MistDim, fontSize = 13.sp)
        }
    }
}

/**
 * Cadastro.
 *
 * Pede o codigo de acesso da empresa de proposito: sem ele qualquer pessoa
 * criaria conta, e cada conversa custa minuto pago de avatar. O codigo diz de
 * qual empresa a pessoa e, e o consumo e contado por empresa.
 */
@Composable
fun RegisterScreen(
    carregando: Boolean,
    errorMessage: String?,
    onCadastrar: (nome: String, email: String, senha: String, codigo: String) -> Unit,
    onIrParaEntrar: () -> Unit,
) {
    var nome by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var senha by remember { mutableStateOf("") }
    var codigo by remember { mutableStateOf("") }

    val valido = AuthStore.emailParece(email) &&
        AuthStore.senhaParece(senha) &&
        codigo.length >= 4

    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 28.dp, vertical = 40.dp),
    ) {
        Cabecalho("Crie a sua conta com o codigo da sua empresa.")

        OutlinedTextField(
            value = nome,
            onValueChange = { nome = it },
            singleLine = true,
            label = { Text("Nome") },
            keyboardOptions = KeyboardOptions(
                capitalization = KeyboardCapitalization.Words,
                imeAction = ImeAction.Next,
            ),
            modifier = Modifier.fillMaxWidth().padding(top = 22.dp),
        )

        OutlinedTextField(
            value = email,
            onValueChange = { email = it.trim() },
            singleLine = true,
            label = { Text("Email") },
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.Email,
                imeAction = ImeAction.Next,
            ),
            modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
        )

        OutlinedTextField(
            value = senha,
            onValueChange = { senha = it },
            singleLine = true,
            label = { Text("Senha") },
            supportingText = {
                Text("Pelo menos ${AuthStore.SENHA_MINIMA} caracteres", fontSize = 11.sp)
            },
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.Password,
                imeAction = ImeAction.Next,
            ),
            modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
        )

        OutlinedTextField(
            value = codigo,
            onValueChange = { codigo = it.filter { c -> c.isLetterOrDigit() }.uppercase().take(16) },
            singleLine = true,
            label = { Text("Codigo da empresa") },
            placeholder = { Text("ABCD2345") },
            keyboardOptions = KeyboardOptions(
                capitalization = KeyboardCapitalization.Characters,
                imeAction = ImeAction.Done,
            ),
            modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
        )

        Erro(errorMessage)

        BotaoPrincipal("Criar conta", valido, carregando) {
            onCadastrar(nome, email, senha, codigo)
        }

        TextButton(onClick = onIrParaEntrar, modifier = Modifier.padding(top = 8.dp)) {
            Text("Ja tenho conta. Quero entrar", color = MistDim, fontSize = 13.sp)
        }
    }
}
