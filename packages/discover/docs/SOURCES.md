# Where each check comes from

Every check maps to a published rule or to a field a search system reads. Sources were fetched on 2026-10-23.

| Check | Source |
|---|---|
| README opening, run command | GitHub, About READMEs: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes |
| Description and topics | GitHub repository search covers name, description and topics by default: https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories ; topics: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/classifying-your-repository-with-topics |
| CITATION.cff | https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-citation-files and https://citation-file-format.github.io/ |
| PyPI keywords, classifiers, URLs | Core metadata: https://packaging.python.org/en/latest/specifications/core-metadata/ ; well-known URLs: https://packaging.python.org/en/latest/specifications/well-known-project-urls/ ; PyPI search fields and boosts: https://github.com/pypi/warehouse/blob/main/warehouse/search/queries.py |
| npm keywords and description | https://docs.npmjs.com/cli/v11/configuring-npm/package-json and https://docs.npmjs.com/searching-for-and-choosing-packages-to-download |
| Title, description, canonical | https://developers.google.com/search/docs/fundamentals/creating-helpful-content and https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls |
| JSON-LD types | https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data , article, software-app and video pages in the same docs |
| Sitemap and robots | https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap and https://developers.google.com/search/docs/crawling-indexing/robots/intro |
| AI search crawlers | OpenAI: https://developers.openai.com/api/docs/bots ; Perplexity: https://docs.perplexity.ai/guides/bots ; Anthropic: https://support.claude.com/en/articles/8896518-about-claude-bot ; Google AI features: https://developers.google.com/search/docs/appearance/ai-features |
| llms.txt | https://llmstxt.org/ . No AI search provider has said it reads the file; Google says no special file is needed for AI features. discover checks it because it is cheap to keep accurate, and claims no ranking effect. |
| Video chapters | https://support.google.com/youtube/answer/9884579 |
| Hashtags | https://support.google.com/youtube/answer/6390658 |
| Titles, descriptions, search | https://support.google.com/youtube/answer/16090438 |
| No engagement bait, no fake engagement | https://support.google.com/youtube/answer/2801973 and https://support.google.com/youtube/answer/3399767 ; Google spam policies: https://developers.google.com/search/docs/essentials/spam-policies |
