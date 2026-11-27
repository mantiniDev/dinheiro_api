# 📱 Painel de Controle (PC → celular)

Transforma o celular (ex.: Redmi Note 10S) num painel que:

- **mostra dados do PC** em tempo real: CPU, RAM, disco, rede, tempo ligado, temperatura/bateria e processos;
- **recebe notificações** no celular (pelo app gratuito **ntfy**), mesmo com a tela desligada;
- **libera ou nega pedidos** com um toque, direto na notificação ou no painel;
- **executa ações** cadastradas por você (bloquear tela, desligar etc.);
- **avisa** quando CPU, RAM ou disco passam do limite.

<img src="print_celular.png" width="300">

## 1. No PC

Precisa de Python 3.10 ou mais novo.

```bash
cd painel
pip install -r requirements.txt
python servidor.py
```

Na primeira vez ele cria o `config.json` com um **token secreto** e mostra algo assim:

```
No celular, abra:  http://192.168.0.10:8765/?token=AbC123...
Tópico ntfy:       painel-1a2b3c4d5e6f
```

> No Windows, aceite o aviso do Firewall para **redes privadas**.

## 2. No celular

1. Conecte no **mesmo Wi-Fi** do PC.
2. Abra o link mostrado no terminal no **Chrome**.
3. Menu ⋮ → **Adicionar à tela inicial**. Ele vira um app em tela cheia.

### Notificações com botões "Liberar / Negar"

1. Instale o **ntfy** (Play Store ou F-Droid).
2. Toque em **+** e inscreva-se no tópico mostrado no terminal (ex.: `painel-1a2b3c4d5e6f`).
3. No `config.json`, preencha `url_publica` com o endereço do PC visto pelo celular,
   por exemplo `"http://192.168.0.10:8765"`, e reinicie o servidor.

> **MIUI:** em *Configurações → Apps → ntfy*, deixe a **Economia de bateria** em *Sem restrições*
> e ative o **Início automático**. Sem isso a MIUI corta as notificações.

## 3. Pedir liberação a partir de qualquer script

```bash
python pedir.py "Liberar internet do PC" "Pedido às 21h"
```

O script fica esperando você tocar em **Liberar** ou **Negar** no celular. Códigos de saída:
`0` = liberado, `1` = negado, `2` = sem resposta (padrão: 300 s, mude com o 3º argumento).

Isso permite encadear com outros comandos:

```bat
python pedir.py "Rodar backup grande" && backup.bat
```

Outros programas também podem pedir liberação via HTTP:

```
POST /api/pedidos            {"titulo": "...", "detalhe": "..."}
GET  /api/pedidos/{id}/aguardar?timeout=60
Cabeçalho: Authorization: Bearer <token>
```

## 4. Cadastrar ações

No `config.json`, em `"acoes"`, cada item vira um botão no painel. Os exemplos que vêm prontos são para
**Windows**. No Linux, troque os comandos, por exemplo `["loginctl", "lock-session"]`.

```json
"abrir_spotify": {
  "nome": "🎵 Spotify",
  "comando": ["cmd", "/c", "start", "spotify:"]
}
```

Use `"confirmar": true` para pedir confirmação antes de executar.
**Só rodam os comandos que estão no arquivo**: o celular não envia comandos livres.

## 5. Acessar fora de casa

Instale o **Tailscale** no PC e no celular (gratuito). Depois use o IP do Tailscale (100.x.x.x)
no link e no `url_publica`. Evite abrir a porta direto no roteador.

## 6. Iniciar junto com o Windows

Crie um atalho para `pythonw servidor.py` (pasta `painel`) dentro de
`shell:startup`. Abra essa pasta com **Win + R**.

## Segurança

- O `token` funciona como uma senha: não compartilhe o link e não suba o `config.json`
  para o GitHub (ele já está no `.gitignore`).
- O tópico do ntfy é público para quem souber o nome. Por isso ele é gerado aleatório, e os
  botões da notificação só funcionam com o token.
- Os pedidos ficam em memória e somem quando o servidor reinicia.
