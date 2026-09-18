import asyncio
import json
import os
from typing import Awaitable, Callable, Optional

import aiohttp
from src.utils.config_manager import ConfigManager

TOKEN_END = "<<END>>"
CEREBRAS_API_URL = "https://api.cerebras.ai/v1/chat/completions"
DEFAULT_CHAT_MODEL = "zai-glm-4.7"
DEFAULT_BACKEND = "cerebras"
DEFAULT_SYSTEM_PROMPT = "Voce e a Mina AI."
MAX_HISTORY = 10


class ChatBridge:
    """Runs the apicomm C binary or Groq chat stream to callbacks."""

    def __init__(self, binary_path: Optional[str] = None, backend: Optional[str] = None):
        self._config = ConfigManager.get_instance()
        llm_opts = self._config.get_config("LLM_OPTIONS", {})
        backend_value = (backend or os.getenv("CHAT_BACKEND") or llm_opts.get("BACKEND") or "groq").lower()
        if backend_value in ("binary", "apicomm"):
            self.backend = "binary"
        else:
            self.backend = backend_value
        if not binary_path:
            try:
                from src.utils.binary_manager import binary_manager
                resolved = binary_manager.ensure_apicomm()
                if resolved:
                    self.binary_path = str(resolved)
                else:
                    self.binary_path = os.path.join(os.path.dirname(__file__), "..", "..", "apicomm")
            except Exception:
                self.binary_path = os.path.join(os.path.dirname(__file__), "..", "..", "apicomm")
        else:
            self.binary_path = binary_path
        self.proc: Optional[asyncio.subprocess.Process] = None
        self._stdout_buffer = ""
        self._in_text_section = False
        self._lock = asyncio.Lock()
        self._history = []
        self._system_prompt = self._load_system_prompt()
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self):
        if self.backend != "binary":
            return
        if self.proc and self.proc.returncode is None:
            return
        try:
            # Inject options as environment variables for the binary
            env = os.environ.copy()
            llm_opts = self._config.get_config("LLM_OPTIONS", {})
            if llm_opts.get("API_KEY"):
                env["CEREBRAS_API_KEY"] = llm_opts["API_KEY"]
            if llm_opts.get("MODEL"):
                env["CEREBRAS_CHAT_MODEL"] = llm_opts["MODEL"]

            self.proc = await asyncio.create_subprocess_exec(
                self.binary_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"apicomm binary not found at {self.binary_path}") from exc

    async def stop(self):
        if self._session and not self._session.closed:
            await self._session.close()
        if self.backend != "binary":
            return
        if self.proc and self.proc.returncode is None:
            self.proc.terminate()
            try:
                await asyncio.wait_for(self.proc.wait(), timeout=2)
            except asyncio.TimeoutError:
                self.proc.kill()
                await self.proc.wait()
        self.proc = None

    def _load_system_prompt(self) -> str:
        prompt_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "prompts.txt")
        if not os.path.exists(prompt_path):
            return DEFAULT_SYSTEM_PROMPT
        with open(prompt_path, "r", encoding="utf-8") as prompt_file:
            prompt = prompt_file.read().strip()
        return prompt or DEFAULT_SYSTEM_PROMPT

    def _append_history(self, role: str, content: str) -> None:
        if not content:
            return
        self._history.append({"role": role, "content": content})
        if len(self._history) > MAX_HISTORY:
            self._history = self._history[-MAX_HISTORY:]

    def _get_system_prompt_with_memories(self, prompt: str = None) -> str:
        from src.utils.memory_db import get_all_memories
        from src.utils.academic_db import get_academic_context
        
        memories = get_all_memories()
        academic_ctx = get_academic_context(prompt)
        
        system_content = self._system_prompt
        
        if academic_ctx:
            system_content += f"\n\n{academic_ctx}"
            
        if memories:
            memory_block = "\n\nCONVERSAS ANTERIORES / MEMÓRIA DO LABORATÓRIO G.E.RA:\n"
            for user, keypoint in memories:
                memory_block += f"- [{user}]: {keypoint}\n"
            system_content += memory_block
        return system_content

    def _build_messages(self, prompt: str) -> list:
        self._append_history("user", prompt)
        messages = [{"role": "system", "content": self._get_system_prompt_with_memories(prompt)}]
        messages.extend(self._history)
        return messages

    async def _process_stream_text(
        self,
        text: str,
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
        on_emotion: Optional[Callable[[str], Awaitable[None]]] = None,
        on_chunk: Optional[Callable[[str, float, Optional[str]], Awaitable[None]]] = None,
        on_control: Optional[Callable[[str], Awaitable[None]]] = None,
    ):
        full_response = ""
        self._stdout_buffer += text

        parts = self._stdout_buffer.split("\n")
        self._stdout_buffer = parts[-1]

        for line in parts[:-1]:
            pline = line.strip()
            # sanitize common literal escape sequences so frontend
            # never sees things like "\\n" or "\\r"
            pline = pline.replace("\\n", " ").replace("\\r", " ").strip()

            if not pline:
                continue

            # handle emotion parameter lines: EMOTION:<name>
            if pline.upper().startswith("EMOTION:"):
                emotion = pline.split(":", 1)[1].strip()
                if on_emotion and emotion:
                    await on_emotion(emotion)
                continue

            # handle control lines like PAUSE:<ms>
            if pline.upper().startswith("PAUSE:"):
                if on_control:
                    await on_control(pline)
                # do not include pause lines in the textual response
                continue

            # handle memory lines: MEMORY|<username>|<keypoint>
            if pline.upper().startswith("MEMORY|"):
                parts = pline.split("|", 2)
                if len(parts) == 3:
                    _, username, keypoint = parts
                    username = username.strip()
                    keypoint = keypoint.strip()
                    if username and keypoint:
                        from src.utils.memory_db import save_memory
                        save_memory(username, keypoint)
                continue

            # check sentinel
            if TOKEN_END in pline:
                before = pline.split(TOKEN_END, 1)[0].strip()
                if before:
                    full_response += before
                    if on_token:
                        await on_token(before)
                return full_response, True

            # handle chunked output with metadata
            if pline.upper().startswith("CHUNK|"):
                fields = pline.split("|", 3)
                if len(fields) == 4:
                    _, delay_str, chunk_emotion, chunk_text = fields
                    try:
                        delay = float(delay_str)
                    except ValueError:
                        delay = 2.5
                    chunk_text = chunk_text.strip()
                    is_done = False
                    if TOKEN_END in chunk_text:
                        chunk_text = chunk_text.split(TOKEN_END, 1)[0].strip()
                        is_done = True
                    if chunk_text:
                        full_response += chunk_text
                        if on_chunk:
                            await on_chunk(chunk_text, delay, chunk_emotion.strip() or None)
                    if is_done:
                        return full_response, True
                continue

            # regular text line
            if pline:
                full_response += pline
                if on_token:
                    await on_token(pline)

        return full_response, False

    async def _send_and_stream_binary(
        self,
        prompt: str,
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
        on_emotion: Optional[Callable[[str], Awaitable[None]]] = None,
        on_chunk: Optional[Callable[[str, float, Optional[str]], Awaitable[None]]] = None,
        on_control: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> str:
        await self.start()
        assert self.proc and self.proc.stdin and self.proc.stdout

        self.proc.stdin.write((prompt + "\n").encode("utf-8"))
        await self.proc.stdin.drain()

        full_response = ""

        while True:
            if self.proc.returncode is not None:
                break
            chunk = await self.proc.stdout.read(256)
            if not chunk:
                break
            text = chunk.decode("utf-8", errors="ignore")
            parsed, done = await self._process_stream_text(
                text,
                on_token=on_token,
                on_emotion=on_emotion,
                on_chunk=on_chunk,
                on_control=on_control,
            )
            full_response += parsed
            if done:
                return full_response

        return full_response

    async def _stream_api_request(
        self,
        api_url: str,
        api_key: str,
        model: str,
        temperature: float,
        max_tokens: int,
        prompt: str,
        backend_name: str,
        on_token=None, on_emotion=None, on_chunk=None, on_control=None
    ) -> str:
        messages = self._build_messages(prompt)
        payload = {
            "model": model,
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": messages,
        }

        full_response = ""
        raw_response = ""
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15, connect=8))

        async with self._session.post(api_url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"{backend_name.upper()} chat error {resp.status}: {body}")

            while True:
                line = await resp.content.readline()
                if not line:
                    break
                text_line = line.decode("utf-8", errors="ignore").strip()
                if not text_line or not text_line.startswith("data:"):
                    continue
                data = text_line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except Exception:
                    continue
                choices = event.get("choices") or []
                if not choices:
                    continue
                content = (choices[0].get("delta") or {}).get("content")
                if not content:
                    continue
                raw_response += content
                parsed, done = await self._process_stream_text(
                    content, on_token=on_token, on_emotion=on_emotion,
                    on_chunk=on_chunk, on_control=on_control
                )
                full_response += parsed
                if done:
                    break

        if self._stdout_buffer:
            parsed, _ = await self._process_stream_text(
                "\n", on_token=on_token, on_emotion=on_emotion,
                on_chunk=on_chunk, on_control=on_control
            )
            full_response += parsed

        if raw_response:
            self._append_history("assistant", raw_response)

        return full_response

    async def _send_and_stream_with_tools(
        self,
        api_url: str,
        api_key: str,
        model: str,
        temperature: float,
        max_tokens: int,
        prompt: str,
        backend_name: str,
        on_token=None, on_emotion=None, on_chunk=None, on_control=None
    ) -> str:
        from src.utils.academic_tools import TOOLS_SCHEMA, execute_academic_tool
        
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20, connect=8))

        system_instruction = (
            "Você é a MABI (Módulo Acadêmico Baseado em Inteligência Artificial), a assistente de voz oficial do Totem da UNESP Sorocaba.\n"
            "DIRETRIZES FUNDAMENTAIS:\n"
            "1. RESPOSTA DE VOZ: Sua resposta será falada em voz alta via sintetizador vocal (TTS). Seja natural, amigável, clara e concisa (1 a 3 frases). Evite markdown elaborado, tabelas ou asteriscos.\n"
            "2. ZERO ALUCINAÇÃO: Você tem ferramentas oficiais (tools) para consultar professores, salas, aulas, calendário escolar e normas acadêmicas. Toda vez que o usuário perguntar sobre a universidade, chame OBRIGATORIAMENTE as ferramentas correspondentes.\n"
            "3. SÍNTESE: Ao receber os dados das ferramentas, resuma as informações essenciais de forma fluida para o aluno."
        )

        messages = [
            {"role": "system", "content": system_instruction}
        ]
        messages.extend(self._history[-MAX_HISTORY:])
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "tools": TOOLS_SCHEMA,
            "tool_choice": "auto",
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        try:
            async with self._session.post(api_url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"{backend_name.upper()} tool calling error {resp.status}: {body}")
                data = await resp.json()
        except Exception as exc:
            return await self._stream_api_request(
                api_url, api_key, model, temperature, max_tokens, prompt, backend_name,
                on_token, on_emotion, on_chunk, on_control
            )

        choice = data["choices"][0]
        msg = choice["message"]
        messages.append(msg)

        if msg.get("tool_calls"):
            if on_emotion:
                await on_emotion("thinking")
            if on_token:
                await on_token("Consultando base acadêmica...")

            for tc in msg["tool_calls"]:
                fn_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except Exception:
                    args = {}
                
                result = await asyncio.to_thread(execute_academic_tool, fn_name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False)
                })

            payload2 = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            async with self._session.post(api_url, json=payload2, headers=headers) as resp2:
                if resp2.status != 200:
                    body2 = await resp2.text()
                    raise RuntimeError(f"{backend_name.upper()} final reply error {resp2.status}: {body2}")
                data2 = await resp2.json()

            final_text = data2["choices"][0]["message"]["content"].strip()
        else:
            final_text = (msg.get("content") or "").strip()

        if on_emotion:
            await on_emotion("neutral")

        import re
        text_clean = re.sub(r'\b(Prof|Profa|Dr|Dra|Sr|Sra)\.\s*', r'\1 ', final_text)
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text_clean) if s.strip()]
        if not sentences:
            sentences = [final_text]

        for s in sentences:
            if on_chunk:
                await on_chunk(s, 2.5, "neutral")
            if on_token:
                await on_token(s + " ")

        self._append_history("user", prompt)
        self._append_history("assistant", final_text)
        return final_text

    async def _send_and_stream_openai(
        self,
        prompt: str,
        on_token=None, on_emotion=None, on_chunk=None, on_control=None
    ) -> str:
        opts = self._config.get_config("LLM_OPTIONS", {})
        bk = self.backend
        
        key = opts.get("API_KEY") or os.getenv(f"{bk.upper()}_API_KEY") or os.getenv("LLM_API_KEY")
        if not key:
            from pathlib import Path
            candidates = [
                Path(".env"),
                Path(__file__).parent.parent.parent / ".env",
                Path(r"C:\Users\Aluno\Hackathon-TV-Box-E10\Projeto Equipe 1\ForgeModules\totem\.env"),
                Path("/root/app/.env")
            ]
            for p in candidates:
                if p.exists():
                    try:
                        with open(p, "r", encoding="utf-8") as f:
                            for line in f:
                                if line.strip().startswith(f"{bk.upper()}_API_KEY="):
                                    key = line.strip().split("=", 1)[1].strip()
                                    if key:
                                        break
                    except Exception:
                        pass
                if key:
                    break

        if not key and bk != "ollama":
            raise RuntimeError(f"API key for {bk} not set.")

        url_map = {
            "cerebras": "https://api.cerebras.ai/v1/chat/completions",
            "groq": "https://api.groq.com/openai/v1/chat/completions",
            "openai": "https://api.openai.com/v1/chat/completions",
            "ollama": "http://localhost:11434/v1/chat/completions"
        }
        url = opts.get("API_URL") or url_map.get(bk, url_map["cerebras"])
        
        model_map = {
            "cerebras": os.getenv("CEREBRAS_CHAT_MODEL") or "zai-glm-4.7",
            "groq": os.getenv("GROQ_CHAT_MODEL") or "openai/gpt-oss-20b",
            "openai": os.getenv("OPENAI_CHAT_MODEL") or "gpt-4o-mini",
            "ollama": os.getenv("OLLAMA_CHAT_MODEL") or "llama3"
        }
        model = opts.get("MODEL") or model_map.get(bk, model_map["cerebras"])

        if bk in ("groq", "openai"):
            return await self._send_and_stream_with_tools(
                url, key, model, opts.get("TEMPERATURE", 0.7), opts.get("MAX_TOKENS", 2048),
                prompt, bk, on_token, on_emotion, on_chunk, on_control
            )

        return await self._stream_api_request(
            url, key, model, opts.get("TEMPERATURE", 0.7), opts.get("MAX_TOKENS", 2048),
            prompt, bk, on_token, on_emotion, on_chunk, on_control
        )

    async def send_and_stream(
        self, prompt: str, on_token=None, on_emotion=None, on_chunk=None, on_control=None
    ) -> str:
        async with self._lock:
            self._stdout_buffer = ""
            self._in_text_section = False
            try:
                if self.backend == "binary":
                    return await self._send_and_stream_binary(prompt, on_token, on_emotion, on_chunk, on_control)
                return await self._send_and_stream_openai(prompt, on_token, on_emotion, on_chunk, on_control)
            except Exception as exc:
                if "429" in str(exc):
                    opts = self._config.get_config("LLM_OPTIONS", {})
                    fb_bk = opts.get("FALLBACK_BACKEND", "groq").lower()
                    if fb_bk:
                        import logging
                        logging.getLogger("src.utils.chat_bridge").warning(f"429 Rate limit on {self.backend}. Falling back to {fb_bk}!")
                        
                        fb_key = os.getenv(f"{fb_bk.upper()}_API_KEY") or os.getenv("LLM_API_KEY") or opts.get("FALLBACK_API_KEY")
                        fb_url = opts.get("FALLBACK_API_URL") or "https://api.groq.com/openai/v1/chat/completions"
                        fb_model = opts.get("FALLBACK_MODEL") or "llama3-8b-8192"
                        
                        # Fix history since _send_and_stream_openai might have appended the user prompt already?
                        # No, _stream_api_request appends history only after sending via _build_messages.
                        # Wait, _build_messages DOES append user prompt! So we must pop it!
                        if self._history and self._history[-1]["role"] == "user" and self._history[-1]["content"] == prompt:
                            self._history.pop()
                            
                        return await self._stream_api_request(
                            fb_url, fb_key, fb_model, opts.get("TEMPERATURE", 0.7), opts.get("MAX_TOKENS", 2048),
                            prompt, fb_bk, on_token, on_emotion, on_chunk, on_control
                        )
                raise exc

    async def read_stderr(self) -> str:
        if self.backend != "binary":
            return ""
        if not self.proc or not self.proc.stderr:
            return ""
        try:
            return (await asyncio.wait_for(self.proc.stderr.read(1024), timeout=0.01)).decode(
                "utf-8", errors="ignore"
            )
        except asyncio.TimeoutError:
            return ""
