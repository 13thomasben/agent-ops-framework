"""
Browser control layer.

Wraps Playwright and exposes a small, stable set of primitives that an LLM can
drive: snapshot the page, click a numbered element, type into it, scroll, etc.

Design notes
------------
* Elements are addressed by integer *refs*, not CSS selectors. Every snapshot
  re-stamps the DOM with `data-wa-ref="N"` attributes. This is what makes the
  agent resilient to class-name churn: it never sees a selector, only "[7]
  button 'Sign in'".
* Refs are invalidated by every navigation and by every snapshot. The agent is
  instructed to re-snapshot after any action that changes the page.
* Secrets are filled by *name*, never by value. `fill_secret` reads the value
  from the environment inside this process. The credential never enters the
  model's context window.
"""

from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

from playwright.sync_api import Page, sync_playwright, TimeoutError as PWTimeout


SNAPSHOT_JS = r"""
() => {
  const SEL = [
    'a', 'button', 'input', 'select', 'textarea', 'summary',
    '[role="button"]', '[role="link"]', '[role="checkbox"]', '[role="radio"]',
    '[role="tab"]', '[role="menuitem"]', '[role="combobox"]', '[role="switch"]',
    '[role="option"]', '[contenteditable="true"]', '[onclick]'
  ].join(', ');

  document.querySelectorAll('[data-wa-ref]').forEach(e => e.removeAttribute('data-wa-ref'));

  const isVisible = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    if (r.bottom < -200 || r.top > window.innerHeight + 3000) return false;
    const s = window.getComputedStyle(el);
    if (s.visibility === 'hidden' || s.display === 'none') return false;
    if (parseFloat(s.opacity || '1') < 0.05) return false;
    return true;
  };

  const nameOf = (el) => {
    const aria = el.getAttribute('aria-label');
    if (aria && aria.trim()) return aria.trim();
    if (el.labels && el.labels.length) {
      const t = (el.labels[0].innerText || '').trim();
      if (t) return t;
    }
    const ph = el.getAttribute('placeholder');
    if (ph && ph.trim()) return ph.trim();
    const txt = (el.innerText || '').trim();
    if (txt) return txt;
    if (typeof el.value === 'string' && el.value.trim() && el.type !== 'password') {
      return el.value.trim();
    }
    const title = el.getAttribute('title');
    if (title && title.trim()) return title.trim();
    const alt = el.getAttribute('alt');
    if (alt && alt.trim()) return alt.trim();
    return el.getAttribute('name') || '';
  };

  let n = 0;
  const lines = [];
  document.querySelectorAll(SEL).forEach((el) => {
    if (!isVisible(el)) return;
    if (el.disabled) return;
    n += 1;
    el.setAttribute('data-wa-ref', String(n));

    const tag = el.tagName.toLowerCase();
    const type = el.getAttribute('type');
    const role = el.getAttribute('role');
    let desc = tag;
    if (type) desc += ':' + type;
    else if (role) desc += ':' + role;

    let extra = '';
    if (tag === 'input' && type === 'password') {
      extra = ' (password field)';
    } else if (tag === 'input' || tag === 'textarea') {
      const cur = (el.value || '');
      extra = cur ? ' (current: "' + cur.slice(0, 40) + '")' : ' (empty)';
    } else if (tag === 'select') {
      const opts = Array.from(el.options || []).slice(0, 20)
        .map(o => o.value).filter(Boolean).join(' | ');
      extra = opts ? ' (options: ' + opts + ')' : '';
    }
    if (el.checked === true) extra += ' [checked]';
    if (el.getAttribute('aria-expanded') === 'true') extra += ' [expanded]';

    const name = nameOf(el).replace(/\s+/g, ' ').slice(0, 110);
    lines.push('[' + n + '] ' + desc + ' "' + name + '"' + extra);
  });

  const bodyText = (document.body ? (document.body.innerText || '') : '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();

  return {
    elements: lines,
    text: bodyText,
    url: location.href,
    title: document.title || '',
    count: n
  };
}
"""


class GuardrailViolation(Exception):
    """Raised when the agent attempts something the task config forbids."""


@dataclass
class BrowserConfig:
    headless: bool = True
    cdp_url: Optional[str] = None          # point at Browserbase / Steel / local CDP
    # Use a Chromium that's already on disk instead of Playwright's own download.
    # Needed wherever `playwright install` can't reach its CDN but the image
    # ships a browser anyway — most managed containers, including Claude Code's.
    executable_path: Optional[str] = None
    viewport_width: int = 1440
    viewport_height: int = 900
    user_agent: Optional[str] = None
    nav_timeout_ms: int = 30_000
    action_timeout_ms: int = 10_000
    storage_state_path: Optional[str] = None   # persist cookies/logins between runs
    downloads_dir: Optional[str] = None
    extra_http_headers: dict = field(default_factory=dict)


class BrowserSession:
    """One browser + one page, with guardrails applied at the action boundary."""

    def __init__(
        self,
        config: BrowserConfig,
        allowed_domains: list[str],
        blocked_keywords: Optional[list[str]] = None,
    ):
        self.config = config
        self.allowed_domains = [d.lower().lstrip(".") for d in allowed_domains]
        self.blocked_keywords = [k.lower() for k in (blocked_keywords or [])]
        self._pw = None
        self._browser = None
        self._context = None
        self.page: Optional[Page] = None
        self.action_log: list[str] = []

    # ---------------- lifecycle ----------------

    def start(self) -> None:
        self._pw = sync_playwright().start()
        cfg = self.config

        if cfg.cdp_url:
            # Remote browser (Browserbase, Steel, Kernel, or a local Chrome
            # launched with --remote-debugging-port).
            self._browser = self._pw.chromium.connect_over_cdp(cfg.cdp_url)
            self._context = (
                self._browser.contexts[0]
                if self._browser.contexts
                else self._browser.new_context()
            )
        else:
            launch_kwargs: dict[str, Any] = {"headless": cfg.headless}
            if cfg.executable_path:
                launch_kwargs["executable_path"] = cfg.executable_path
            self._browser = self._pw.chromium.launch(**launch_kwargs)
            ctx_kwargs: dict[str, Any] = {
                "viewport": {"width": cfg.viewport_width, "height": cfg.viewport_height},
                "accept_downloads": True,
            }
            if cfg.user_agent:
                ctx_kwargs["user_agent"] = cfg.user_agent
            if cfg.storage_state_path and os.path.exists(cfg.storage_state_path):
                ctx_kwargs["storage_state"] = cfg.storage_state_path
            self._context = self._browser.new_context(**ctx_kwargs)

        if cfg.extra_http_headers:
            self._context.set_extra_http_headers(cfg.extra_http_headers)

        self._context.set_default_timeout(cfg.action_timeout_ms)
        self._context.set_default_navigation_timeout(cfg.nav_timeout_ms)

        self.page = self._context.pages[0] if self._context.pages else self._context.new_page()

    def stop(self, save_state: bool = True) -> None:
        try:
            if save_state and self.config.storage_state_path and self._context:
                os.makedirs(
                    os.path.dirname(self.config.storage_state_path) or ".", exist_ok=True
                )
                self._context.storage_state(path=self.config.storage_state_path)
        except Exception:
            pass
        for closer in (self._context, self._browser):
            try:
                if closer:
                    closer.close()
            except Exception:
                pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

    def __enter__(self) -> "BrowserSession":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    # ---------------- guardrails ----------------

    def _check_domain(self, url: str) -> None:
        if not self.allowed_domains:
            return
        host = (urlparse(url).hostname or "").lower()
        for allowed in self.allowed_domains:
            if allowed == "*" or host == allowed or host.endswith("." + allowed):
                return
        raise GuardrailViolation(
            f"Navigation to '{host}' is blocked. This task's allowed_domains are: "
            f"{', '.join(self.allowed_domains)}. If you need this domain, the task "
            f"config must be updated by a human."
        )

    def _check_keywords(self, label: str) -> None:
        low = (label or "").lower()
        for kw in self.blocked_keywords:
            if kw in low:
                raise GuardrailViolation(
                    f"Refusing to click element labelled '{label}': it matches the "
                    f"blocked keyword '{kw}'. This action needs human approval."
                )

    def _locator(self, ref: int):
        return self.page.locator(f'[data-wa-ref="{ref}"]')

    def _label_of(self, ref: int) -> str:
        try:
            return (self._locator(ref).inner_text(timeout=1500) or "").strip()
        except Exception:
            try:
                return self._locator(ref).get_attribute("aria-label") or ""
            except Exception:
                return ""

    def _log(self, msg: str) -> None:
        self.action_log.append(f"{time.strftime('%H:%M:%S')} {msg}")

    def _settle(self, ms: int = 900) -> None:
        """Give SPAs a moment to re-render after an interaction."""
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=5_000)
        except PWTimeout:
            pass
        self.page.wait_for_timeout(ms)

    # ---------------- primitives ----------------

    def snapshot(self, max_text_chars: int = 4000, max_elements: int = 200) -> str:
        data = self.page.evaluate(SNAPSHOT_JS)
        elements = data["elements"][:max_elements]
        truncated_els = len(data["elements"]) - len(elements)
        text = data["text"][:max_text_chars]
        truncated_text = len(data["text"]) > max_text_chars

        parts = [
            f"URL: {data['url']}",
            f"TITLE: {data['title']}",
            "",
            f"INTERACTIVE ELEMENTS ({len(elements)} shown"
            + (f", {truncated_els} more not shown — scroll to reveal" if truncated_els > 0 else "")
            + "):",
        ]
        parts.extend(elements or ["(none found)"])
        parts.append("")
        parts.append("PAGE TEXT:")
        parts.append(text or "(empty)")
        if truncated_text:
            parts.append(
                f"\n(text truncated at {max_text_chars} chars — "
                "scroll down and re-snapshot to read more)"
            )
        return "\n".join(parts)

    def navigate(self, url: str) -> str:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        self._check_domain(url)
        self.page.goto(url, wait_until="domcontentloaded")
        self._settle()
        self._log(f"navigate {url}")
        return f"Navigated to {self.page.url}"

    def click(self, ref: int) -> str:
        label = self._label_of(ref)
        self._check_keywords(label)
        self._locator(ref).first.click(timeout=self.config.action_timeout_ms)
        self._settle()
        self._check_domain(self.page.url)
        self._log(f"click [{ref}] '{label[:60]}'")
        return f"Clicked [{ref}] '{label[:60]}'. Page is now {self.page.url}. Re-snapshot to see the result."

    def type_text(self, ref: int, text: str, submit: bool = False) -> str:
        loc = self._locator(ref).first
        loc.click(timeout=self.config.action_timeout_ms)
        loc.fill("")
        loc.type(text, delay=25)
        if submit:
            loc.press("Enter")
            self._settle()
            self._check_domain(self.page.url)
        self._log(f"type [{ref}] '{text[:40]}' submit={submit}")
        return (
            f"Typed into [{ref}]"
            + (" and pressed Enter. Re-snapshot to see the result." if submit else ".")
        )

    def fill_secret(self, ref: int, secret_env_var: str, submit: bool = False) -> str:
        """Fill a field from an env var. The value is never returned to the model."""
        value = os.environ.get(secret_env_var)
        if value is None:
            raise GuardrailViolation(
                f"Secret '{secret_env_var}' is not set in the environment. "
                f"Cannot fill this field."
            )
        loc = self._locator(ref).first
        loc.click(timeout=self.config.action_timeout_ms)
        loc.fill(value)
        if submit:
            loc.press("Enter")
            self._settle()
        self._log(f"fill_secret [{ref}] <{secret_env_var}>")
        return f"Filled [{ref}] with the value of {secret_env_var} (value withheld)."

    def select_option(self, ref: int, value: str) -> str:
        self._locator(ref).first.select_option(value)
        self._settle(400)
        self._log(f"select [{ref}] = {value}")
        return f"Selected '{value}' in [{ref}]."

    def scroll(self, direction: str = "down", amount: int = 800) -> str:
        dy = amount if direction == "down" else -amount
        self.page.mouse.wheel(0, dy)
        self.page.wait_for_timeout(500)
        self._log(f"scroll {direction} {amount}")
        return f"Scrolled {direction} by {amount}px. Re-snapshot to see newly visible content."

    def go_back(self) -> str:
        self.page.go_back(wait_until="domcontentloaded")
        self._settle()
        self._log("back")
        return f"Went back. Now at {self.page.url}"

    def wait_for(self, text: Optional[str] = None, seconds: float = 2.0) -> str:
        if text:
            try:
                self.page.get_by_text(text, exact=False).first.wait_for(timeout=15_000)
                self._log(f"wait_for text '{text}'")
                return f"Text '{text}' appeared."
            except PWTimeout:
                return f"Timed out after 15s waiting for text '{text}'. It may not be present."
        self.page.wait_for_timeout(int(min(seconds, 15) * 1000))
        return f"Waited {seconds}s."

    def screenshot_b64(self, full_page: bool = False) -> str:
        png = self.page.screenshot(full_page=full_page, type="png")
        self._log("screenshot")
        return base64.b64encode(png).decode("ascii")
