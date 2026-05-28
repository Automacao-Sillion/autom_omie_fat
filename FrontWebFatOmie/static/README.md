# Pasta de arquivos estáticos

Arquivos colocados aqui são servidos pelo Streamlit em `/app/static/`.

## Como usar

Em qualquer template HTML, referencie:
```html
<img src="app/static/nome-do-arquivo.svg" />
```

## Arquivos esperados

- `logo-sillion.svg` — logo da Sillion (versão preta, será invertida para branco via CSS)

## Como baixar o logo da Sillion

Abra o PowerShell **na pasta do projeto** e rode:

```powershell
Invoke-WebRequest -Uri "https://www.sillion.com.br/wp-content/themes/sillion/images/logo-black-tm.svg" -OutFile "static/logo-sillion.svg"
```

Ou no terminal Git Bash / WSL:

```bash
curl -o static/logo-sillion.svg "https://www.sillion.com.br/wp-content/themes/sillion/images/logo-black-tm.svg"
```

Ou simplesmente: abra o link no navegador, clique com botão direito → "Salvar como…" → salve na pasta `static/` com o nome `logo-sillion.svg`.
