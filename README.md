# MenteAcessível SP

Geolocalizador de serviços públicos de saúde mental no **Estado de São Paulo**. O app
encontra o CAPS, a UBS ou o serviço 24h mais adequado e mais próximo, mostra
endereço, telefone, turno e documentos, e tem um painel que aponta onde falta CAPS.

- **Menu inicial** (`/`): ligação direta para o CVV 188 e o SAMU 192, busca por
  localização ou CEP, atalhos por perfil e acesso ao painel e às informações.
- **Busca** (`/buscar`): por GPS, CEP, endereço ou cidade, com filtros por perfil (adulto,
  criança/adolescente, álcool e drogas, crise 24h).
- **Botão de crise** sempre visível: CVV 188, SAMU 192 e o serviço 24h mais próximo.
- **Triagem orientativa** com 3 perguntas, que só escolhe o filtro e não faz diagnóstico.
- **Ficha da unidade:** compartilhamento por WhatsApp e reporte de erro.
- **Como chegar**, em três modos:
  - **A pé** e **de carro:** rota calculada no próprio app (OSRM/OpenStreetMap), com tempo, distância, desenho no mapa e passo a passo em português.
  - **Ônibus/metrô:** abre o Google Maps ou o Moovit com a rota de transporte público.
  - A aba inicial é "a pé" quando a unidade fica a até 1,5 km; acima disso, transporte público.
- **Painel analítico** (`/painel`):
  - mapa coroplético da cobertura de CAPS por município;
  - as 20 regiões com menor cobertura;
  - dispersão de população × cobertura;
  - tabela de déficit por porte do município;
  - demanda registrada no app.
- **PWA:** pode ser instalado no celular e mostra a última busca sem internet.

O backend usa **apenas a biblioteca padrão do Python**, então não há nada para instalar.

---

## Como rodar no VS Code

**Pré-requisito:** Python 3.10 ou mais novo ([python.org](https://www.python.org/downloads/)).
No Windows, marque a opção "Add Python to PATH" na instalação.

1. Extraia o zip e abra a pasta `menteacessivel-sp` no VS Code (**Arquivo > Abrir Pasta**).
2. Aceite instalar as extensões recomendadas (Python e Debugger).
3. Abra o painel **Executar e Depurar** (Ctrl+Shift+D) e rode, nesta ordem:
   - **1. Coletar dados (CNES + IBGE):** baixa e prepara os dados de SP. Leva alguns
     minutos, porque a API do CNES entrega 20 registros por vez e são milhares de UBS.
   - **2. Rodar o servidor:** depois abra <http://127.0.0.1:8000> no navegador.
     Essa é a tela inicial; a busca com o mapa fica em <http://127.0.0.1:8000/buscar>.
4. Para rodar os testes: **3. Rodar os testes**, ou a aba **Testes** (ícone de frasco).

Também dá para usar o terminal do VS Code (Ctrl+`):

```bash
python -m etl.coletar          # 1. baixa CNES + IBGE e cria dados/menteacessivel.db
python -m app.servidor         # 2. sobe o site em http://127.0.0.1:8000
python -m unittest discover -s tests -t . -v   # testes
```

> No macOS/Linux, use `python3` no lugar de `python`.

### Se a API do CNES estiver fora do ar

Use a base completa do CNES em CSV:

1. No site do CNES (cnes.datasus.gov.br), em **Serviços > Download**, baixe
   `BASE_DE_DADOS_CNES_AAAAMM.ZIP`.
2. Extraia o zip em `dados/cnes_csv/`.
3. Rode `python -m etl.coletar --cnes-csv dados/cnes_csv` (ou a configuração **1b** no VS Code).

Para recriar o banco sem baixar nada de novo (por exemplo, depois de editar a curadoria),
rode `python -m etl.coletar --somente-carregar`.

---

## Usar no celular

Rode **um comando só** (com o computador ligado):

```
python -m app.celular
```

No VS Code, também dá para usar **"0. Abrir no celular"** no painel Executar e Depurar.

O comando faz três coisas:

1. Liga o servidor.
2. Cria um link **HTTPS** temporário com o Cloudflare Tunnel (gratuito, sem cadastro).
   - Na primeira vez, pergunta se pode baixar o programa `cloudflared` (cerca de 60 MB,
     do GitHub oficial da Cloudflare) para a pasta `ferramentas/`.
   - O link funciona no 4G, não precisa mexer no Firewall e libera o GPS do celular.
3. Abre no computador a página `http://127.0.0.1:8000/celular`, com um **QR code**.

No Android:

1. Aponte a **câmera** (ou o Google Lens) para o QR code e toque no link.
2. Se der erro, espere 20 segundos e recarregue: o link leva um tempinho para ativar.
3. Para instalar, toque no menu **⋮ > Instalar app** no Chrome.

Cuidados:

- O link muda a cada execução.
- O link para de funcionar quando você fecha o terminal.
- Qualquer pessoa com o link consegue abrir o app: use para testes.

### Se não funcionar

| Problema | Solução |
| --- | --- |
| "A porta 8000 já está em uso" | Feche o outro servidor (Ctrl+C) ou rode `python -m app.celular --porta 8001` |
| Não gera o link HTTPS | Verifique a internet do computador. Antivírus ou rede da faculdade/empresa podem bloquear o Cloudflare; use a alternativa por Wi-Fi |
| Celular mostra erro do Cloudflare | Espere 20–30 segundos e recarregue |
| Alternativa por Wi-Fi não abre | Celular e computador precisam estar na **mesma** Wi-Fi (não a de convidados). Libere a porta no Firewall com o comando que o terminal mostra, num PowerShell **como administrador** |

Só pela Wi-Fi, sem link HTTPS: `python -m app.celular --sem-tunel`. Nesse caso o GPS não
funciona, mas a busca por CEP ou cidade funciona.

### Instalar na tela inicial

- **Android (Chrome):** menu **⋮ > Instalar app**, ou o botão **Instalar no celular** no menu do app.
- **iPhone (Safari):** **Compartilhar > Adicionar à Tela de Início**.

---

## Fontes de dados

| Fonte | O que vem dela | Como é obtida |
| --- | --- | --- |
| CNES (Ministério da Saúde) | CAPS (tipo 70), pronto atendimento/UPA (73), UBS (2) e postos (1) de SP: nome, endereço, telefone, coordenadas, turno | API `apidadosabertos.saude.gov.br/cnes/estabelecimentos`, ou CSV da base completa |
| IBGE – Localidades | 645 municípios de SP, região imediata e intermediária | `servicodados.ibge.gov.br/api/v1/localidades` |
| IBGE – Censo 2022 | População residente por município (tabela 4709) | `servicodados.ibge.gov.br/api/v3/agregados` |
| IBGE – Malhas | Polígonos dos municípios (GeoJSON) | `servicodados.ibge.gov.br/api/v3/malhas` |
| Curadoria própria | Horários verificados e documentos exigidos | `dados/curadoria/*.csv` |

No navegador, endereços são localizados pelo **ViaCEP** e pelo **Nominatim**
(OpenStreetMap). O mapa de fundo é do OpenStreetMap.

### Curadoria (o que o CNES não tem)

- `dados/curadoria/horarios.csv`: horários verificados por telefone. Uma linha por
  dia e faixa, com `dia_semana` de 0 (segunda) a 6 (domingo). Exemplo:
  `1234567;0;08:00;17:00;Acolhimento até 16h;2026-11-10`
- `dados/curadoria/documentos.csv`: documentos padrão (`chave = padrao`) ou
  específicos de uma unidade (`chave = código CNES`).

Depois de editar, rode `python -m etl.coletar --somente-carregar` e reinicie o servidor.

---

## Como funciona por dentro

```
dados públicos ──► etl/ (coleta, limpeza, classificação) ──► SQLite ──► app/servidor.py (API) ──► web/ (PWA + painel)
```

| Pasta/arquivo | Papel |
| --- | --- |
| `etl/fonte_cnes_api.py` | Pagina a API do CNES; detecta sozinho se `offset` conta itens ou páginas |
| `etl/fonte_cnes_csv.py` | Importador alternativo da base CSV |
| `etl/fonte_ibge.py` | Municípios, população (com plano B na estimativa anual) e malha |
| `etl/carregar.py` | Converte o código de município de 6 para 7 dígitos, corrige coordenadas trocadas ou fora do município e grava no banco |
| `app/classificacao.py` | Deduz a modalidade do CAPS (I, II, III, AD, AD III, IJ) pelo nome e pelo turno |
| `app/kdtree.py` | **KD-tree 3D** para os k vizinhos mais próximos |
| `app/geo.py` | Haversine, **ponto-em-polígono** (ray casting) e centroide (shoelace) |
| `app/busca.py` | Busca em duas etapas e busca textual tolerante a erros |
| `app/cobertura.py` | Indicador oficial CAPS/100 mil hab. e déficit por porte |
| `app/rotas.py` | Rotas de carro e a pé (OSRM), tradução das instruções e links de transporte público |
| `app/servidor.py` | API REST e arquivos estáticos (`http.server`) |
| `app/celular.py` | Comando que abre o app no celular (túnel HTTPS + QR code) |
| `web/inicio.html` | Menu inicial |
| `web/index.html` + `app.js` | Busca, mapa, ficha e "Como chegar" (`/buscar`) |
| `web/painel.html` + `painel.js` | Painel de cobertura (`/painel`) |
| `web/` (demais) | Estilo, PWA (manifest, service worker, ícones) e "Sobre" |

### Algoritmo de busca

1. **Candidatos (k-NN):** cada unidade vira um vetor 3D na esfera unitária. A
   distância em linha reta entre vetores cresce junto com a distância real sobre a
   Terra, então uma KD-tree comum acha os vizinhos exatos em cerca de O(log n), em
   vez de comparar com todas as unidades. A busca só aceita unidades compatíveis
   com o perfil e amplia o raio (30 → 60 → 120 → 250 km) até achar pelo menos 3.
2. **Ranking:** `S = 0,40·compatibilidade + 0,35·(1 − d/dmax) + 0,15·aberto_agora + 0,10·mesmo_município`.
   Os pesos ficam em `app/config.py`.
3. **Município do usuário:** ponto-em-polígono sobre a malha do IBGE, com
   pré-filtro por caixa envolvente. Só o código do município é registrado, nunca a
   coordenada.

### Indicador de cobertura (Ministério da Saúde)

`(0,5×CAPS I + CAPS II + CAPSi + CAPS AD + 1,5×(CAPS III + CAPS AD III)) ÷ população × 100.000`

| Faixa | Classificação |
| --- | --- |
| acima de 0,70 | Muito boa |
| 0,50 a 0,70 | Boa |
| 0,35 a 0,49 | Regular/baixa |
| 0,20 a 0,34 | Baixa |
| abaixo de 0,20 | Insuficiente/crítica |

O déficit por porte usa os parâmetros de implantação: acima de 15 mil hab., CAPS I;
acima de 70 mil, CAPS II, AD e i; acima de 150 mil, CAPS III e AD III.

### API

| Rota | Descrição |
| --- | --- |
| `GET /api/unidades/proximas?lat=&lon=&perfil=&limite=` | Ranking das unidades mais indicadas |
| `GET /api/unidades/busca?q=&municipio=&perfil=` | Busca por nome ou bairro |
| `GET /api/unidades/{cnes}` | Ficha completa |
| `GET /api/unidades/caps` | Todos os CAPS, para a camada do mapa |
| `GET /api/municipios` | Municípios com centro e população |
| `GET /api/cobertura` | Indicadores por município, região e estado |
| `GET /api/malha` | GeoJSON dos municípios |
| `GET /api/demanda` | Buscas registradas (anônimas) |
| `POST /api/reportes` | `{"cnes", "tipo", "texto"}` para reportar erro |
| `GET /api/rota?cnes=&modo=&lat=&lon=` | Rota até a unidade. `modo`: `transporte`, `carro` ou `a_pe` |
| `GET /api/status` | Situação do banco e data dos dados |

Perfis válidos: `todos`, `adulto`, `infantojuvenil`, `alcool_drogas`, `crise`.

### Atalhos da tela de busca

O menu inicial abre a busca com parâmetros na URL:

| Parâmetro | Efeito |
| --- | --- |
| `perfil=adulto` | Já marca o perfil escolhido |
| `acao=localizacao` | Pede o GPS e busca na hora |
| `q=01310-100` | Busca o CEP, endereço ou cidade informado |
| `triagem=1` | Abre as 3 perguntas da triagem |
| `tipos=1` | Abre a explicação "O que é um CAPS?" |
| `crise=1` | Abre o aviso de crise |

Exemplo: `/buscar?perfil=infantojuvenil&acao=localizacao`.

---

## Privacidade (LGPD)

- Sem login, nome ou CPF.
- A localização é usada na requisição e descartada.
- O banco guarda só o município, o perfil, a hora arredondada e se havia serviço perto.
- As respostas da triagem ficam só no navegador.
- Os reportes pedem para não incluir dados pessoais e têm limite de 500 caracteres.
- No "Como chegar" de carro ou a pé, o ponto de partida é enviado pelo nosso servidor ao
  routing.openstreetmap.de, sem identificar a pessoa. A rota fica só num cache em memória.

## Limitações conhecidas

- A **modalidade do CAPS** vem do nome cadastrado. Nomes fora do padrão viram
  "CAPS (modalidade não identificada)", com peso 1 no indicador. Para precisão total,
  cruze com as habilitações do CNES (próximo passo sugerido).
- **Horários** não verificados são estimados pelo turno do CNES e aparecem como
  "provavelmente aberto".
- Unidades **sem coordenada** no CNES ficam no centro do município, com aviso na ficha.
- A agregação regional usa as **regiões imediatas do IBGE**. Para usar as regiões de
  saúde (DRS), preencha a coluna `regiao_saude` da tabela `municipio`.
- **Rotas de carro e a pé** usam o servidor comunitário da FOSSGIS. Ele é gratuito,
  mas sem garantia de funcionamento, e sua política proíbe uso pesado. Se cair, o app
  oferece os links do Google Maps e do Waze. Para muitos usuários, rode um OSRM próprio
  ou contrate um serviço de rotas.
- O tempo de carro não considera o trânsito, e o **transporte público** depende do
  Google Maps ou do Moovit (não há serviço gratuito sem chave para calcular dentro do app).
- O servidor `http.server` é bom para desenvolvimento e piloto. Para produção, use
  um servidor WSGI/ASGI atrás de HTTPS.

## Próximos passos sugeridos

1. Cruzar com o arquivo de habilitações do CNES (HB) para confirmar a modalidade dos CAPS.
2. Usar o tempo de trajeto (a pé ou de transporte) no ranking, e não só a distância em linha reta.
3. Migrar para PostgreSQL + PostGIS quando houver vários usuários simultâneos.
4. Tela de moderação dos reportes colaborativos.
5. Revisão do conteúdo de crise por profissional de saúde mental antes de publicar.
