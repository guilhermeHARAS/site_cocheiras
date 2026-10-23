# Cocheira RADAMÉS

Sistema de acompanhamento da jornada dos cavalos: Cruzas, Potros, Em treinamento e Tropa pronta.

## Estrutura

- `frontend/`: HTML, estilos, JavaScript, ícones e PWA.
- `backend/`: servidor HTTP, API, autenticação, regras das etapas, assistente de consultas e persistência.
- `backend/data/`: banco JSON usado somente quando o servidor roda sem PostgreSQL.

## Dados antigos

Ao carregar um banco do primeiro protótipo, a migração mantém contas, senhas protegidas, sessões, IDs, campos dos cavalos e contagens de treinos. As fotos individuais foram descontinuadas e removidas por uma migração autorizada, sempre precedida por backup. Cavalos antigos sem etapa são classificados em `Em treinamento`; aqueles com 60 treinos ou mais não são movidos automaticamente. A migração é idempotente e não inventa data de nascimento para idades aproximadas.

Antes de cada migração de formato, o servidor salva automaticamente uma cópia integral do estado bruto na tabela `app_state_backups`. O hash do conteúdo impede cópias duplicadas quando o servidor reinicia. No PostgreSQL, contas, sessões, cavalos, despesas e controles contra cliques repetidos ficam em tabelas próprias e indexadas. A primeira migração confere as quantidades antes de ser confirmada. O servidor mantém uma cópia de leitura em memória e grava cada alteração no PostgreSQL antes de responder. Durante a estabilização, `app_state` também é atualizado nas gravações para permitir retorno seguro à versão anterior.

## Pergunte à Cocheira

O assistente local responde, em modo somente leitura, perguntas sobre filiação, etapas, idades, treinos e nascimentos previstos. Ele não depende de serviço externo, não envia os dados do clube a terceiros e não pode alterar cadastros.

Exemplos:

- `Quais são os filhos do Trovão?`
- `Quantos filhos Trovão tem?` — se necessário, o assistente pergunta se deve procurar como pai, mãe ou nos dois campos.
- `Quais filhos do pai Trovão estão em treinamento?`
- `Quantos cavalos estão em treinamento?`
- `Quem já atingiu 60 treinos?`
- `Qual a idade de Aurora?`

## Executar

No terminal, dentro desta pasta:

```powershell
python backend/app.py
```

O navegador abrirá em `http://127.0.0.1:8000`. Ao iniciar pelo `iniciar.bat`, a janela também mostra o endereço que deve ser aberto em celulares conectados ao mesmo Wi-Fi. Cada responsável pode usar **Criar conta** com seu próprio e-mail e senha. A sessão permanece ativa no aparelho por até 90 dias, inclusive quando o servidor reinicia.

Para habilitar o banco PostgreSQL e a leitura de Excel no computador, instale os pacotes com `pip install -r requirements.txt`. Na nuvem, o Render faz essa instalação automaticamente.

## Testes

```powershell
py -m unittest discover -s tests -p "test_*.py" -v
node tests\test_frontend.mjs
```

## Publicação gratuita

O projeto inclui `render.yaml` para publicar o servidor gratuitamente no Render e usa Supabase Postgres para manter os dados.

1. Crie um projeto gratuito no Supabase.
2. Em **Connect**, copie a conexão **Session pooler** e substitua `[YOUR-PASSWORD]` pela senha do banco.
3. Envie este projeto para um repositório GitHub.
4. No Render, crie um **Blueprint** usando o repositório.
5. Quando solicitado, informe somente a senha do banco do Supabase na variável secreta `DATABASE_PASSWORD`.

Não coloque a conexão do banco dentro do código ou do GitHub.
## Cadastro rápido

Em cada etapa, o botão **Cadastro rápido** permite:

- importar planilhas Excel (`.xlsx`) ou CSV com reconhecimento de nomes alternativos de colunas;
- ditar os dados pelo microfone em navegadores compatíveis;
- fotografar documentos e extrair o texto para conferência;
- colar anotações ou abrir arquivos `.txt` do Bloco de Notas.

Toda entrada passa por uma prévia editável. É possível cadastrar um animal somente com o nome; nascimento e idade são solicitados, mas opcionais. Listas simples com uma linha por animal, contendo apenas `Nome` ou `Nome - idade`, também são reconhecidas. Nomes já existentes no banco ou repetidos na própria importação são destacados para o usuário e nenhum dado é gravado antes da confirmação. Se a planilha tiver uma coluna `Etapa`, ela pode distribuir os registros entre Cruzas, Potros, Em treinamento e Tropa pronta; sem essa coluna, é usada a etapa atualmente aberta.

Em textos e documentos sem rótulos, linhas consecutivas com filiação, idade ou data completam o animal iniciado na primeira linha; uma linha em branco começa outro animal. Exemplo: `Persa`, `Duelo x Leide`, `3 anos`, linha em branco, `Estrela`. Em planilhas, linhas sem nome podem completar o último cavalo nomeado, e a prévia informa quais linhas foram reunidas. Interpretações ambíguas, como `Persa Duelo x Leide`, ficam desmarcadas e exigem conferência.
