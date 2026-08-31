import re

with open("src/utils/tts_client.py", "r") as f:
    content = f.read()

# Add functools import if not there
if "from functools import lru_cache" not in content:
    content = content.replace("from typing import Optional, Callable", "from typing import Optional, Callable\nfrom functools import lru_cache")

# Add regex definitions
if "_MULTI_DOTS_RE =" not in content:
    # Insert after logger = get_logger(__name__)
    content = content.replace("logger = get_logger(__name__)", "logger = get_logger(__name__)\n\n_MULTI_DOTS_RE = re.compile(r'\\.{2,}')\n_SPACED_DOTS_RE = re.compile(r'\\.\\s*\\.\\s*\\.\\s*')")

# Patch _normalize_text
old_normalize = """    def _normalize_text(self, text: str) -> str:
        if not text:
            return ""
        # Remove espaços duplos ou quebras de linha
        text = " ".join(text.split())

        # Substitui múltiplos pontos/reticências por "..."
        text = re.sub(r'\\.{2,}', '...', text)

        # Garante que haja um espaço após pontuações comuns
        for punct in [".", ",", "!", "?", ";", ":"]:
            text = text.replace(f" {punct}", punct)
            text = text.replace(punct, f"{punct} ")

        # Corrige reticências espaçadas (ex: ". . .") geradas pelo loop anterior de volta para "..."
        text = re.sub(r'\\.\\s*\\.\\s*\\.\\s*', '... ', text)

        # Reduz espaços repetidos gerados
        text = " ".join(text.split())

        # Garante que o texto termine com alguma pontuação para fechar a entonação
        if text and text[-1] not in [".", "!", "?", "..."]:
            if not text.endswith("..."):
                text += "."

        return text.strip()"""

new_normalize = """    @staticmethod
    @lru_cache(maxsize=1024)
    def _normalize_text(text: str) -> str:
        if not text:
            return ""
        # Remove espaços duplos ou quebras de linha
        text = " ".join(text.split())

        # Substitui múltiplos pontos/reticências por "..."
        text = _MULTI_DOTS_RE.sub('...', text)

        # Garante que haja um espaço após pontuações comuns
        for punct in [".", ",", "!", "?", ";", ":"]:
            text = text.replace(f" {punct}", punct)
            text = text.replace(punct, f"{punct} ")

        # Corrige reticências espaçadas (ex: ". . .") geradas pelo loop anterior de volta para "..."
        text = _SPACED_DOTS_RE.sub('... ', text)

        # Reduz espaços repetidos gerados
        text = " ".join(text.split())

        # Garante que o texto termine com alguma pontuação para fechar a entonação
        if text and text[-1] not in [".", "!", "?", "..."]:
            if not text.endswith("..."):
                text += "."

        return text.strip()"""

if old_normalize in content:
    content = content.replace(old_normalize, new_normalize)
else:
    print("Could not find old normalize_text")

content = content.replace("text = self._normalize_text(text)", "text = self._normalize_text(text)")

with open("src/utils/tts_client.py", "w") as f:
    f.write(content)
