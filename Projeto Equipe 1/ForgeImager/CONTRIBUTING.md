# Contribuindo para o Forge Imager

Contribuições são muito bem-vindas. Algumas formas de ajudar:

- Relate bugs [abrindo uma issue](https://github.com/multi-forge/multi-forge/issues)
- Sugira novos recursos (e abra uma discussão primeiro se for uma mudança grande)
- Envie pull requests para correções e melhorias
- Adicione ou melhore traduções em `src/locales/`
- Melhore a documentação para facilitar o início de outros desenvolvedores

Para configuração do ambiente de desenvolvimento, instruções de compilação e estrutura do projeto, consulte o guia [DEVELOPMENT.md](DEVELOPMENT.md).

## Fluxo de Trabalho de Desenvolvimento

1. Faça um fork do repositório.
2. Crie uma branch de recurso (`git checkout -b feature/recurso-incrivel`).
3. Faça suas alterações e execute as verificações de qualidade abaixo.
4. Faça o commit utilizando mensagens no padrão convencional (Conventional Commits).
5. Envie a branch para o seu fork (`git push origin feature/recurso-incrivel`).
6. Abra um Pull Request.

### Nomenclatura de branch

Adicione um prefixo à branch indicando o tipo de alteração: `feature/` para novas funcionalidades, `fix/` para correção de bugs, `docs/` para documentação, `refactor/` para reestruturação de código.

### Mensagens de commit

Utilize a especificação [Conventional Commits](https://www.conventionalcommits.org/): `<tipo>(<escopo>): <assunto>`.

Os tipos válidos são `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `build`, `ci`. Os escopos comuns são `frontend`, `backend`, `flash`, `device`, `i18n`, `build`, `ci`, `docs`. Mantenha cada commit focado em uma única alteração lógica e escreva o assunto no modo imperativo ("adiciona modo escuro", em vez de "adicionado modo escuro").

## Verificações de Qualidade

O CI executa essas validações em cada pull request, portanto, execute-as localmente antes de enviar.

Frontend, após alterar qualquer arquivo dentro de `src/`:

```bash
npm run lint        # Executa ESLint
npx tsc --noEmit    # Validação de tipos TypeScript
```

Backend, após alterar qualquer arquivo dentro de `src-tauri/`:

```bash
cd src-tauri
cargo fmt           # Não deve produzir nenhuma diferença (diff)
cargo clippy --all-targets --all-features -- -D warnings
```

Um PR precisa de zero erros de lint e zero avisos (warnings) para ser integrado.

## Traduções

O aplicativo suporta 18 idiomas: `de`, `en`, `es`, `fr`, `hr`, `it`, `ja`, `ko`, `nl`, `pl`, `pt`, `pt-BR`, `ru`, `sl`, `sv`, `tr`, `uk`, `zh`. Observe que `pt` (Português de Portugal) e `pt-BR` (Português do Brasil) são tratados como idiomas separados.

Ao adicionar ou remover uma chave de tradução, atualize todos os 18 arquivos em `src/locales/` para que mantenham o mesmo conjunto de chaves. PRs que deixarem chaves ausentes em algum arquivo não passarão na revisão.

## Outras formas de contribuir

* [Abra uma discussão](https://github.com/multi-forge/multi-forge/discussions)
* [Ajude membros da comunidade](https://github.com/multi-forge/multi-forge/discussions)
