# Buscador de passagens Smiles ✈️ 🇪🇺

Procura todos os dias passagens **em milhas Smiles** do Brasil para a Europa
(e, se você quiser, as voltas também). Quando encontra trechos dentro do seu
limite de milhas, avisa por **Telegram** e/ou **e-mail**.

- Configure rotas, datas e limite de milhas em [`config.yaml`](config.yaml).
- Por padrão você só recebe ofertas **novas** ou que **ficaram mais baratas** desde a última busca.
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

## 2. Configurar os avisos

### Telegram (recomendado)
1. No Telegram, fale com **@BotFather**, envie `/newbot` e guarde o **token**.
2. Mande qualquer mensagem para o seu bot novo.
3. Fale com **@userinfobot** para descobrir o seu **chat id**.

### E-mail (Gmail)
1. Ative a verificação em duas etapas na sua conta Google.
2. Crie uma **senha de app** em <https://myaccount.google.com/apppasswords>.
3. Use seu e-mail como `SMTP_USUARIO` e a senha de app como `SMTP_SENHA`.
   Para outro provedor, defina também `SMTP_HOST` e `SMTP_PORTA` (SSL).

## 3. Rodar todo dia

### Opção A: no seu computador (mais confiável)
A Smiles costuma bloquear servidores na nuvem, mas aceita a internet de casa.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium

export TELEGRAM_BOT_TOKEN="..."    # Windows: set TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID="..."
python buscador.py --testar-notificacao   # confere se o aviso chega
python buscador.py                        # faz a busca
```

Para agendar a execução diária:
- **Linux/Mac (cron)**: `crontab -e` e adicione
  `0 7 * * * cd /caminho/Buscador-de-passagens && .venv/bin/python buscador.py >> busca.log 2>&1`
  (coloque as variáveis `TELEGRAM_...` no topo do crontab).
- **Windows**: no *Agendador de Tarefas*, crie uma tarefa diária que execute
  `C:\caminho\Buscador-de-passagens\.venv\Scripts\python.exe buscador.py`
  com "Iniciar em" apontando para a pasta do projeto.

### Opção B: GitHub Actions (grátis, sem deixar o PC ligado)
O workflow [`busca-diaria.yml`](.github/workflows/busca-diaria.yml) roda todo dia às 07:17
(horário de Brasília) e salva o histórico em `dados/`.

1. Em **Settings → Secrets and variables → Actions**, cadastre os secrets
   `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` e/ou `SMTP_USUARIO`, `SMTP_SENHA` e `EMAIL_PARA`.
2. Em **Actions → Busca diária Smiles → Run workflow**, rode uma vez para testar.
3. Se a Smiles bloquear os servidores do GitHub, você recebe um aviso de falha.
   Nesse caso use a Opção A.

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
