# ForgePrompt Phase 7 — ToolRegistryAdapter
#
# Provides a registry of callable tools for the ReAct reasoning loop.
# Built-in tools are fully wired (no mocks):
#   - system_ping          : Health / environment check.
#   - memory_search        : Full-text search across working + semantic memory.
#   - web_search           : DuckDuckGo HTML scrape (same approach as app.py).
#   - http_fetch           : GET any public URL and return a text preview.
#   - read_file            : Read a file from disk (sandboxed to uploads dir).
#   - write_file           : Write text content to a file (sandboxed).
#   - run_python_sandbox   : Execute code via the SandboxService if available.
#   - llm_generate         : One-shot LLM call via the container's LLMService.

import logging
import os
import re
import time
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict

from services.service_result import ServiceResult
from services.errors import ForgeError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sandbox root — tool file I/O is restricted to this directory.
# ---------------------------------------------------------------------------
_SANDBOX_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static", "uploads"))


def _safe_path(relative_path: str) -> str:
    """Resolve *relative_path* under the sandbox root.  Raises on path traversal."""
    abs_path = os.path.abspath(os.path.join(_SANDBOX_ROOT, relative_path))
    if not abs_path.startswith(_SANDBOX_ROOT):
        raise PermissionError(f"Path traversal attempt blocked: {relative_path!r}")
    return abs_path


class ToolRegistryAdapter:
    def __init__(self, container):
        self.container = container
        self.tools: Dict[str, Dict[str, Any]] = {}
        self._register_default_tools()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def _register_default_tools(self) -> None:
        self.register_tool(
            name="system_ping",
            description="Returns the current system health status including UTC time.",
            func=self._tool_system_ping,
        )
        self.register_tool(
            name="memory_search",
            description=(
                "Searches the agent's working memory and semantic memory for entries "
                "matching the given query string.  Args: query (str)."
            ),
            func=self._tool_memory_search,
        )
        self.register_tool(
            name="web_search",
            description=(
                "Queries DuckDuckGo and returns up to 5 result snippets.  "
                "Args: query (str)."
            ),
            func=self._tool_web_search,
        )
        self.register_tool(
            name="http_fetch",
            description=(
                "Fetches a public URL via HTTP GET and returns the first 2000 characters "
                "of the response body.  Args: url (str)."
            ),
            func=self._tool_http_fetch,
        )
        self.register_tool(
            name="read_file",
            description=(
                "Reads a text file from the sandbox uploads directory.  "
                "Args: filename (str) — relative path inside uploads/."
            ),
            func=self._tool_read_file,
        )
        self.register_tool(
            name="write_file",
            description=(
                "Writes text content to a file in the sandbox uploads directory.  "
                "Args: filename (str), content (str)."
            ),
            func=self._tool_write_file,
        )
        self.register_tool(
            name="run_python_sandbox",
            description=(
                "Executes a Python code snippet in the sandboxed environment and "
                "returns stdout, stderr, and any returned outputs dict.  "
                "Args: code (str)."
            ),
            func=self._tool_run_python_sandbox,
        )
        self.register_tool(
            name="llm_generate",
            description=(
                "Calls the container LLMService to generate a response for a given "
                "prompt.  Args: prompt (str), system_prompt (str, optional), "
                "max_tokens (int, optional)."
            ),
            func=self._tool_llm_generate,
        )

    def register_tool(self, name: str, description: str, func: Callable) -> ServiceResult:
        try:
            if name in self.tools:
                raise ForgeError(f"Tool '{name}' already registered in the registry.")
            self.tools[name] = {"name": name, "description": description, "func": func}
            logger.info("Registered tool: %s", name)
            return ServiceResult.ok(data={"registered": name})
        except ForgeError as fe:
            logger.error("[ToolRegistryAdapter] register_tool failed: %s", fe)
            return ServiceResult.fail(error_code="TOOL_ALREADY_REGISTERED", message=str(fe))
        except Exception as exc:
            logger.error("[ToolRegistryAdapter] register_tool failed: %s", exc)
            return ServiceResult.fail(error_code="TOOL_REGISTRATION_FAILED", message=str(exc))

    def get_available_tools(self) -> ServiceResult:
        try:
            tool_list = [
                {"name": t["name"], "description": t["description"]}
                for t in self.tools.values()
            ]
            return ServiceResult.ok(data=tool_list)
        except Exception as exc:
            logger.error("[ToolRegistryAdapter] get_available_tools failed: %s", exc)
            return ServiceResult.fail(error_code="GET_TOOLS_FAILED", message=str(exc))

    def execute_tool(self, name: str, args: Dict[str, Any]) -> ServiceResult:
        try:
            if name not in self.tools:
                raise ForgeError(f"Tool '{name}' not found in registry.")
            tool_func = self.tools[name]["func"]
            logger.info("Executing tool '%s' with args: %s", name, args)
            result = tool_func(**args)
            return ServiceResult.ok(data=result)
        except ForgeError as fe:
            logger.warning("[ToolRegistryAdapter] Tool not found: %s", fe)
            return ServiceResult.fail(error_code="TOOL_NOT_FOUND", message=str(fe))
        except Exception as exc:
            logger.error("[ToolRegistryAdapter] execute_tool '%s' failed: %s", name, exc)
            return ServiceResult.fail(error_code="TOOL_EXECUTION_FAILED", message=str(exc))

    # ------------------------------------------------------------------
    # Built-in tool implementations
    # ------------------------------------------------------------------

    def _tool_system_ping(self, **kwargs) -> Dict[str, Any]:
        """Returns current system status and UTC timestamp."""
        import datetime
        return {
            "status": "online",
            "utc_time": datetime.datetime.utcnow().isoformat() + "Z",
            "pid": os.getpid(),
            "message": "System is operational.",
        }

    def _tool_memory_search(self, query: str = "", **kwargs) -> Dict[str, Any]:
        """
        Searches the agent's working memory and semantic memory for *query*.
        Returns matching entries ranked by relevance (simple substring match).
        """
        query_lower = query.lower().strip()
        results = []

        # Attempt to reach the container's AgentMemory if available.
        memory = getattr(self.container, "agent_memory", None)
        if memory is None:
            # Try to pull memory from a reasoning engine on the container.
            reasoning = getattr(self.container, "reasoning_engine", None)
            if reasoning is not None:
                memory = getattr(reasoning, "memory", None)

        if memory is not None:
            # Search working memory
            for entry in getattr(memory, "working_memory", []):
                content = str(entry.get("content", ""))
                if query_lower in content.lower():
                    results.append({
                        "source": "working_memory",
                        "role": entry.get("role"),
                        "content": content[:300],
                        "importance": entry.get("importance", 1.0),
                    })
            # Search semantic memory
            for key, val in getattr(memory, "semantic_memory", {}).items():
                blob = f"{key} {val.get('value', '')}".lower()
                if query_lower in blob:
                    results.append({
                        "source": "semantic_memory",
                        "key": key,
                        "value": str(val.get("value", ""))[:300],
                    })

        return {
            "query": query,
            "match_count": len(results),
            "results": results[:10],
        }

    def _tool_web_search(self, query: str = "", **kwargs) -> Dict[str, Any]:
        """
        Queries DuckDuckGo HTML and returns up to 5 result snippets.
        This is the same scraping technique used in the main workflow engine.
        """
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as resp:
                html = resp.read().decode("utf-8", errors="replace")

            raw = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
            snippets = [re.sub(r"<[^>]+>", "", s).strip() for s in raw[:5]]
            return {
                "query": query,
                "result_count": len(snippets),
                "results": snippets,
            }
        except Exception as exc:
            logger.warning("[tool:web_search] fetch failed: %s", exc)
            return {"query": query, "result_count": 0, "results": [], "error": str(exc)}

    def _tool_http_fetch(self, url: str = "", **kwargs) -> Dict[str, Any]:
        """
        Fetches a public URL and returns the first 2000 characters of the
        response body as plain text.
        """
        if not url:
            raise ValueError("url argument is required for http_fetch.")
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "ForgePrompt-Agent/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.status
                body = resp.read().decode("utf-8", errors="replace")
            return {
                "url": url,
                "status_code": status,
                "content_preview": body[:2000],
                "truncated": len(body) > 2000,
            }
        except Exception as exc:
            logger.warning("[tool:http_fetch] request failed: %s", exc)
            return {"url": url, "status_code": None, "content_preview": "", "error": str(exc)}

    def _tool_read_file(self, filename: str = "", **kwargs) -> Dict[str, Any]:
        """
        Reads a text file from the sandboxed uploads directory.
        Path traversal is blocked.
        """
        if not filename:
            raise ValueError("filename is required for read_file.")
        abs_path = _safe_path(filename)
        if not os.path.isfile(abs_path):
            raise FileNotFoundError(f"File not found in sandbox: {filename!r}")
        with open(abs_path, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
        return {
            "filename": filename,
            "size_bytes": len(content.encode("utf-8")),
            "content": content[:4000],
            "truncated": len(content) > 4000,
        }

    def _tool_write_file(self, filename: str = "", content: str = "", **kwargs) -> Dict[str, Any]:
        """
        Writes *content* to a file in the sandboxed uploads directory.
        Path traversal is blocked.
        """
        if not filename:
            raise ValueError("filename is required for write_file.")
        abs_path = _safe_path(filename)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return {
            "filename": filename,
            "size_bytes": len(content.encode("utf-8")),
            "status": "written",
        }

    def _tool_run_python_sandbox(self, code: str = "", **kwargs) -> Dict[str, Any]:
        """
        Executes *code* through the SandboxService if it is available on the
        container.  Falls back to a safe restricted exec() if not.
        """
        if not code:
            raise ValueError("code is required for run_python_sandbox.")

        sandbox_service = None
        try:
            from services.sandbox_service import SandboxService
            sandbox_service = SandboxService
        except ImportError:
            pass

        if sandbox_service is not None:
            result = sandbox_service.execute_code(code, inputs=kwargs)
            return result if isinstance(result, dict) else {"output": str(result)}

        # Minimal fallback — restricted exec with captured stdout.
        import io
        import contextlib

        _forbidden = ("import os", "import sys", "import subprocess", "__import__", "open(", "eval(", "exec(")
        for token in _forbidden:
            if token in code:
                raise PermissionError(f"Forbidden construct in sandbox code: {token!r}")

        stdout_capture = io.StringIO()
        local_ns: Dict[str, Any] = {}
        try:
            with contextlib.redirect_stdout(stdout_capture):
                exec(compile(code, "<sandbox>", "exec"), {"__builtins__": {}}, local_ns)  # noqa: S102
        except Exception as exc:
            return {"success": False, "stdout": stdout_capture.getvalue(), "stderr": str(exc), "outputs": {}}

        # Collect any non-private, JSON-serialisable values from local_ns.
        outputs = {}
        for k, v in local_ns.items():
            if not k.startswith("_"):
                try:
                    import json
                    json.dumps(v)
                    outputs[k] = v
                except (TypeError, ValueError):
                    outputs[k] = str(v)

        return {
            "success": True,
            "stdout": stdout_capture.getvalue(),
            "stderr": "",
            "outputs": outputs,
        }

    def _tool_llm_generate(
        self,
        prompt: str = "",
        system_prompt: str = "",
        max_tokens: int = 1000,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Calls the container's LLMService.generate() method.
        Falls back to a direct LLMService.call() if the container method is
        unavailable, keeping the tool functional in all configurations.
        """
        if not prompt:
            raise ValueError("prompt is required for llm_generate.")

        # Try container-level llm_service first (preferred path).
        llm_service = getattr(self.container, "llm_service", None)
        if llm_service is not None and hasattr(llm_service, "generate"):
            result = llm_service.generate(prompt=prompt, system_prompt=system_prompt or None)
            if result.is_success:
                return {"text": result.data, "source": "container_llm"}
            raise RuntimeError(result.error_message or "LLM generation failed.")

        # Direct fallback via the module-level LLMService.
        try:
            from services.llm_service import LLMService
            res = LLMService.call(
                provider_name="groq",
                model_name="llama-3.3-70b-versatile",
                prompt=prompt,
                system_prompt=system_prompt or None,
                max_tokens=max_tokens,
            )
            return {"text": res["text"], "tokens": res.get("tokens", 0), "source": res.get("source", "llm")}
        except Exception as exc:
            raise RuntimeError(f"LLM generate tool failed: {exc}") from exc
