"""Verify the real demo HTML offline with a trace from native HTTP integration.

Requires Playwright only in the environment executing this optional check.
The browser receives a fake fetch/popup boundary: this is a UI test, not a claim
of browser-to-server end-to-end authentication. No HTTP navigation is attempted.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

FIXTURE_CODE = r"""
import json, re, sys
from pathlib import Path
from fastapi.testclient import TestClient
from govbr_auth.fake import create_fake_app
from govbr_auth.runtime import GovBrRuntimeSettings, GovBrProvider
from govbr_auth.fake.debug.presentation import render_debug_page
out=Path(sys.argv[1])
out.joinpath("debug-preview.html").write_text(render_debug_page("/auth/govbr/login"), encoding="utf-8")
app=create_fake_app(GovBrRuntimeSettings(provider=GovBrProvider.FAKE))
headers={"X-Govbr-Demo":"1","Origin":"http://127.0.0.1:8000"}
with TestClient(app,base_url="http://127.0.0.1:8000") as client:
    assert client.post("/govbr-auth-demo/debug/trace",headers=headers).status_code==201
    login=client.get("/auth/govbr/login",follow_redirects=False)
    form=client.get(login.headers["location"])
    artifact=re.search(r'name="request" value="([^"]+)"',form.text)[1]
    auth=client.post("/fake-govbr/login",data={"request":artifact,"cpf":"11122233344","password":"senha-ficticia"},follow_redirects=False)
    assert client.get(auth.headers["location"]).status_code==200
    trace=client.get("/govbr-auth-demo/debug/trace",headers=headers).json()
    out.joinpath("ui-trace.json").write_text(json.dumps(trace,ensure_ascii=False,indent=2),encoding="utf-8")
"""


def main() -> None:
    from playwright.sync_api import sync_playwright, expect

    parser = argparse.ArgumentParser(
        description="Verify demo UI offline; never navigate an HTTP URL."
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="Directory outside the checkout"
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Interpreter with govbr-auth and its test extras",
    )
    parser.add_argument(
        "--browser",
        help="Optional Chromium executable; defaults to Playwright's browser",
    )
    args = parser.parse_args()
    out = args.output.resolve()
    if out.is_relative_to(Path(__file__).resolve().parents[1]):
        parser.error("--output must be outside the checkout")
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run([args.python, "-c", FIXTURE_CODE, str(out)], check=True, timeout=60)
    html = out.joinpath("debug-preview.html").read_text(encoding="utf-8")
    trace = json.loads(out.joinpath("ui-trace.json").read_text(encoding="utf-8"))
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=args.browser, headless=True, args=["--no-sandbox"]
        )
        context = browser.new_context(
            viewport={"width": 1500, "height": 1100}, accept_downloads=True
        )
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))

        def load(*, blocked=False, fail=False, reduced=False):
            page.emulate_media(reduced_motion="reduce" if reduced else "no-preference")
            page.goto("about:blank")
            page.evaluate(
                """([fixture, blocked, fail]) => {
        window.__calls = []; window.__fixture=fixture; window.__blocked=blocked; window.__fail=fail;
        window.open=()=>blocked?null:{closed:false,location:{replace:()=>{}},focus:()=>{},close(){this.closed=true;}};
        window.fetch=async(url,opts)=>{window.__calls.push(opts.method);if(fail)throw new Error('network');
          const data=opts.method==='POST'?{...fixture,events:[],completed:false}:fixture;
          return {ok:true,status:opts.method==='DELETE'?204:200,json:async()=>JSON.parse(JSON.stringify(data))};};
      }""",
                [trace, blocked, fail],
            )
            page.set_content(html)
            expect(page.locator("#start")).to_be_enabled()

        load()
        page.screenshot(path=str(out / "desktop-final-initial.png"), full_page=True)
        page.locator("#start").click()
        expect(page.locator("#capture-state")).to_have_text("Captura concluída")
        page.locator("#play").click()
        expect(page.locator("#play")).to_have_text("Reproduzir")
        page.locator('[data-phase="token"]').click()
        assert page.evaluate("document.activeElement.dataset.phase") == "token"
        page.locator("#tab-http").click()
        expect(page.locator("#technical-content")).to_contain_text("Basic [oculto]")
        expect(page.locator("#technical-content")).to_contain_text("access_token")
        assert page.locator("#wire").get_attribute("d") == "M300 65 H500"
        assert page.locator("#wire-response").get_attribute("d") == "M500 96 H300"
        assert page.locator(".actor.active").evaluate_all(
            "(nodes)=>nodes.map(n=>n.id).sort()"
        ) == ["actor-backend", "actor-provider"]
        page.wait_for_timeout(300)
        page.screenshot(path=str(out / "desktop-final-technical.png"), full_page=True)
        page.locator("#tab-http").press("ArrowRight")
        expect(page.locator("#tab-data")).to_be_focused()
        expect(page.locator("#tab-data")).to_have_attribute("aria-selected", "true")
        page.locator("#next").click()
        expect(page.locator("#stage-title")).to_contain_text("Buscar chaves")
        page.locator("#previous").click()
        expect(page.locator("#stage-title")).to_contain_text("servidores")
        with page.expect_download() as downloaded:
            page.locator("#export").click()
        path = out / "exported-ui-trace.json"
        downloaded.value.save_as(path)
        assert json.loads(path.read_text()) == trace
        before = page.evaluate("window.__calls.slice()")
        page.locator("#speed").select_option("800")
        page.locator("#replay").click()
        expect(page.locator("#play")).to_have_text("Pausar")
        page.wait_for_timeout(900)
        expect(page.locator("#event-position")).to_contain_text("1 de")
        page.locator("#play").click()
        assert page.evaluate("window.__calls") == before, "replay must not resend HTTP"
        page.locator("#clear").click()
        expect(page.locator("#capture-state")).to_have_text("Captura apagada")
        expect(page.locator("#export")).to_be_disabled()
        assert page.evaluate("window.__calls.at(-1)") == "DELETE"
        load(blocked=True)
        page.locator("#start").click()
        expect(page.locator("#capture-state")).to_have_text("Janela bloqueada")
        assert page.evaluate("window.__calls") == []
        load(fail=True)
        page.locator("#start").click()
        expect(page.locator("#capture-state")).to_have_text("Não foi possível iniciar")
        expect(page.locator("#start")).to_be_enabled()
        load(reduced=True)
        page.locator("#start").click()
        expect(page.locator("#capture-state")).to_have_text("Captura concluída")
        expect(page.locator("#play")).to_have_text("Reproduzir")
        page.locator("#next").click()
        assert "animate" not in page.locator("#packet").get_attribute("class")
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate(
            "document.documentElement.scrollWidth <= innerWidth"
        ), "horizontal overflow"
        page.screenshot(path=str(out / "mobile-final.png"), full_page=True)
        assert not errors, errors
        context.close()
        browser.close()
        print(
            "PASS: offline Chromium controls, keyboard, redacted export, no replay HTTP, popup/network failure, reduced motion, mobile overflow; real auth separately tested"
        )


if __name__ == "__main__":
    main()
