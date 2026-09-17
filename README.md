# Cocheira RADAMÉS

Sistema local para cadastro de cavalos e controle de treinos, organizado em frontend e backend.

## Estrutura

- `frontend/`: HTML, estilos, JavaScript, ícones e PWA.
- `backend/`: servidor HTTP, API, autenticação e persistência.
- `backend/data/`: banco de dados JSON criado automaticamente no primeiro uso.

## Executar

No terminal, dentro desta pasta:

```powershell
python backend/app.py
```

O navegador abrirá em `http://127.0.0.1:8000`. No primeiro acesso, cadastre o e-mail e a senha do responsável.

Para executar somente no computador, não é necessário instalar pacotes. Na nuvem, o Render instala automaticamente o conector PostgreSQL listado em `requirements.txt`.

## Publicação gratuita

O projeto inclui `render.yaml` para publicar o servidor gratuitamente no Render e usa Supabase Postgres para manter os dados.

1. Crie um projeto gratuito no Supabase.
2. Em **Connect**, copie a conexão **Session pooler** e substitua `[YOUR-PASSWORD]` pela senha do banco.
3. Envie este projeto para um repositório GitHub.
4. No Render, crie um **Blueprint** usando o repositório.
5. Quando solicitado, informe a conexão do Supabase na variável secreta `DATABASE_URL`.

Não coloque a conexão do banco dentro do código ou do GitHub.
