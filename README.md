# Buscador de passagens Smiles ✈️ 🇪🇺

Procura todos os dias passagens **em milhas Smiles** de São Paulo (GRU) para França,
Luxemburgo, Alemanha, Bélgica, Holanda e Suíça, com as voltas também. Todo dia manda
um **e-mail** com o que encontrou dentro do seu limite de milhas.

- Configure rotas, datas e limite de milhas em [`config.yaml`](config.yaml).
- O e-mail traz todas as ofertas do dia. Para receber só as novas ou as que ficaram mais baratas, use `so_novidades: true`.
- Cada execução salva um CSV em `dados/resultados/AAAA-MM-DD.csv`.

> As milhas mostradas são por adulto e por trecho. **Taxas de embarque não estão incluídas.**
> O buscador só pesquisa. A emissão você faz no site ou no app da Smiles.

## 1. Configurar a busca

Abra o `config.yaml` e ajuste:

| Campo | O que faz |
|---|---|
| `origens` / `destinos` | Códigos dos aeroportos (GRU, GIG, LIS, MAD, CDG…) |
| `datas` | Janela de datas: relativa a hoje ou com `inicio`/`fim` fixos |
| `intervalo_dias` | Pesquisa uma data a cada N dias (quanto maior, menos buscas) |
| `volta` | Busca também Europa → Brasil, `duracao_viagem_dias` depois da ida |
| `max_milhas` | Limite de milhas por trecho |
| `max_paradas`, `cabine`, `companhias` | Filtros extras |
| `clube_smiles` | `true` usa o preço de assinante do Clube Smiles |

Total de buscas = origens × destinos × datas (× 2 com a volta). Mantenha esse número
na casa das centenas. Muitas buscas seguidas fazem a Smiles bloquear o acesso.

## 2. Instalar no seu computador

A busca roda no seu computador porque a Smiles bloqueia servidores na nuvem, como o
GitHub. O computador precisa estar ligado e com internet no horário da busca
(07:17). Se estiver desligado, a busca roda assim que você ligar no Windows, ou quando
o Mac acordar.

Antes de tudo, instale o **Python 3** em <https://www.python.org/downloads/>.
No Windows, marque a opção **"Add python.exe to PATH"** na instalação.

Depois baixe este projeto: no GitHub, clique em **Code → Download ZIP** e descompacte
numa pasta fixa, por exemplo `C:\buscador-de-passagens` ou `~/buscador-de-passagens`.
No Mac, evite as pastas Documentos, Mesa e Downloads, porque o agendador do sistema
não tem permissão de acessá-las.

### Windows
1. Dê dois cliques em **`instalar_windows.bat`**. Ele instala tudo e cria a tarefa
   "Buscador Smiles" no Agendador de Tarefas.
2. O Bloco de Notas abre o arquivo `.env`. Preencha o e-mail e a senha de app (veja o passo 3) e salve.
3. Dê dois cliques em **`testar_email_windows.bat`** para conferir se o e-mail chega.
4. Para fazer uma busca agora, dê dois cliques em **`rodar_windows.bat`**.
   O andamento fica no arquivo `busca.log`.

Para desligar a busca diária, abra o **Agendador de Tarefas**, encontre "Buscador Smiles"
e escolha **Desabilitar** ou **Excluir**.

### Mac ou Linux
No Terminal, dentro da pasta do projeto:
```bash
bash instalar.sh
```
Depois preencha o `.env` e teste:
```bash
.venv/bin/python buscador.py --testar-notificacao   # e-mail de teste
.venv/bin/python buscador.py                        # busca agora
```
Para desligar: no Mac, `launchctl unload ~/Library/LaunchAgents/br.buscador-smiles.plist`.
No Linux, `crontab -e` e apague a linha `# buscador-smiles`.

## 3. Configurar o e-mail (Gmail)

1. Ative a **verificação em duas etapas** na sua conta Google.
2. Crie uma **senha de app** em <https://myaccount.google.com/apppasswords>.
   O Google mostra 16 letras.
3. No arquivo `.env` da pasta do projeto, preencha:
   ```
   SMTP_USUARIO=seu.email@gmail.com
   SMTP_SENHA=as16letrasdasenhadeapp
   ```
   `EMAIL_PARA` é opcional. Vazio, o e-mail vai para você mesmo.
   O `.env` fica só no seu computador e nunca é enviado ao GitHub.

Você recebe um e-mail por dia com as passagens encontradas e a planilha anexada.
Se quiser avisos também pelo Telegram, preencha `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`.
Crie o bot com **@BotFather** e descubra o chat id com **@userinfobot**.

> O workflow do GitHub Actions continua no repositório, mas **sem agendamento**.
> Só roda se você mandar manualmente, e a Smiles bloqueia os servidores do GitHub.

## Como funciona

O `modo: auto` tenta primeiro a API que o próprio site da Smiles usa (rápido).
Se ela for bloqueada, abre o site num Chrome automatizado (Playwright) e lê o
resultado da busca. Para ver o navegador funcionando, rode com `MOSTRAR_NAVEGADOR=1`.

```
python buscador.py --sem-notificar   # busca sem enviar avisos
python -m pytest                     # testes (pip install -r requirements-dev.txt)
```

## Avisos

- A API da Smiles não é oficial nem documentada. Ela pode mudar ou passar a bloquear
  robôs a qualquer momento.
- Use com moderação (uma execução por dia, com pausa entre buscas) e para uso pessoal.
- Sempre confira preço e disponibilidade no site antes de emitir.
