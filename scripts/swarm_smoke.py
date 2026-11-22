"""Check /#swarm on a running app. Uses read-only API requests and an intercepted live submission.

    python scripts/swarm_smoke.py [BASE_URL] --channel chrome
"""
import argparse
import json
import re

from playwright.sync_api import expect, sync_playwright


def check_live_intake(page, view, inspector, roster):
    inspector.get_by_role("button", name="Run", exact=True).click()
    expect(inspector.get_by_role("radio")).to_have_count(0)
    subject = inspector.get_by_label("Subject", exact=True)
    submit = inspector.get_by_role("button", name="Open a live Payment case")
    expect(submit).to_be_disabled()
    subject.fill("  ")
    expect(submit).to_be_disabled()
    subject.fill("Smoke test")
    expect(submit).to_be_enabled()
    inspector.get_by_label("Contact profile URL", exact=False).fill("https://example.org/contact")
    expect(submit).to_be_disabled()
    inspector.get_by_role("checkbox").check()
    expect(submit).to_be_enabled()

    inspector.get_by_role("tab", name="Candidate").click()
    submit = inspector.get_by_role("button", name="Open a live Candidate case")
    expect(subject).to_have_value("")
    subject.fill("Smoke test")
    inspector.get_by_role("checkbox").check()
    for label, value in [("Candidate profile URL", "https://example.org/contact"),
                         ("Claimed employer domain", "example.org"), ("Claim from the CV", "Engineer")]:
        expect(submit).to_be_disabled()
        inspector.get_by_label(label).fill(value)
    expect(submit).to_be_enabled()
    inspector.get_by_role("checkbox").uncheck()
    expect(submit).to_be_disabled()

    inspector.get_by_role("tab", name="Payment").click()
    subject.fill("  Smoke test  ")
    agent = next(a for a in roster if a["id"] == "identity")
    events = [
        {"type": "step", "agent_id": agent["id"], "name": agent["name"], "event": phase, "status": status}
        for phase, status in [("start", "running"), ("end", "complete")]
    ]
    case = {"id": "browser-smoke", "mode": "live", "desk": "payment", "subject": "Smoke test",
            "verdict": "HELD", "receipt": "0123456789abcdef", "swarm_roster": roster,
            "swarm_events": events, "swarm_reports": [events[-1]]}
    submissions = []

    def respond(route):
        submissions.append((route.request.method, route.request.post_data_json))
        messages = [*events, {"type": "case", "case": case}]
        route.fulfill(content_type="application/x-ndjson", body="\n".join(json.dumps(m) for m in messages))

    page.route("**/api/cases/stream", respond)
    inspector.get_by_role("button", name="Open a live Payment case").click()
    expect(inspector.get_by_text(case["receipt"], exact=True)).to_be_visible()
    assert submissions == [("POST", {"desk": "payment", "mode": "live", "subject": "Smoke test",
                                    "inputs": {}, "consent": False})]
    expect(view.locator(".motion-control")).to_contain_text("Recorded trace")
    summary = f"1 of {len(roster)} agent reports"
    expect(inspector.get_by_text("Recorded trace · " + summary, exact=True)).to_be_visible()
    inspector.get_by_role("button", name="Replay handoffs").click()
    expect(inspector.get_by_text("Recorded playback", exact=False)).to_be_visible()
    expect(inspector.get_by_text("Recorded trace · " + summary, exact=True)).to_be_visible()
    expect(inspector.get_by_role("button", name=re.compile("^Identity resolver")).first).to_contain_text("Done")


def test_camera(page, view, diagram, *, mobile, reduced):
    meter = view.get_by_role("button", name="Fit entire map")
    map_layer = diagram.locator(".map-geometry")
    def origin():
        return map_layer.evaluate("""el => {
            const m = new DOMMatrixReadOnly(getComputedStyle(el).transform);
            return [m.e, m.f];
        }""")

    expect(meter).to_have_text("100%")
    if reduced:
        assert diagram.evaluate("el => el.getAnimations({subtree:true}).filter(a=>a.effect?.getTiming().duration>1).length") == 0
    else:
        page.wait_for_function("window.entranceStages.has('atlas-enter-trace')", timeout=3500)
        page.wait_for_function("!document.querySelector('.atlas-entering')", timeout=3500)
        stages=page.evaluate("Array.from(window.entranceStages)")
        assert set(stages) >= {"atlas-enter-orbit","atlas-enter-strip","atlas-enter-trace","atlas-enter-name"}

    view.get_by_role("button", name="Zoom in", exact=True).click()
    expect(meter).not_to_have_text("100%")
    meter.click()
    expect(meter).to_have_text("100%")

    center = diagram.evaluate("""svg => {
        const point = new DOMPoint(450,365).matrixTransform(svg.getScreenCTM());
        return {x:point.x, y:point.y};
    }""")
    x, y = center["x"], center["y"]
    if mobile:
        touch = page.context.new_cdp_session(page)
        def pinch(state, distance):
            points = [] if distance is None else [{"x":x-distance,"y":y,"id":0},{"x":x+distance,"y":y,"id":1}]
            touch.send("Input.dispatchTouchEvent", {"type":state,"touchPoints":points})
        pinch("touchStart", 25)
        pinch("touchMove", 45)
        pinch("touchEnd", None)
        expect(meter).not_to_have_text("100%")
        touch.detach()
    else:
        page.mouse.move(x+20,y)
        page.mouse.wheel(0,-160)
        expect(meter).not_to_have_text("100%")
        page.wait_for_timeout(600)
        start = origin()
        page.mouse.move(x,y)
        page.mouse.down()
        page.mouse.move(x+72,y+38,steps=8)
        page.mouse.up()
        page.wait_for_timeout(600)
        assert sum(abs(a-b) for a,b in zip(start,origin())) > 10, "Drag did not pan the map"
        expect(view.get_by_label("Agent inspector")).to_be_hidden()
    meter.click()
    expect(meter).to_have_text("100%")


def check_view(browser, url, *, mobile=False, reduced=False):
    page = browser.new_page(viewport={"width": 390 if mobile else 1440, "height": 844 if mobile else 900},
                            is_mobile=mobile, has_touch=mobile, service_workers="block", reduced_motion="reduce" if reduced else "no-preference")
    page.set_default_timeout(3500)
    page.route("**/api/**", lambda r: r.continue_() if r.request.method == "GET" else r.abort())
    page.add_init_script("""window.entranceStages=new Set();
      document.addEventListener('animationstart',e=>{
        if(e.animationName.startsWith('atlas-enter-'))window.entranceStages.add(e.animationName);
      },true);""")
    page.goto(url, wait_until="domcontentloaded", timeout=8000)
    page.reload(wait_until="domcontentloaded")
    view = page.get_by_role("region", name="Agent swarm workflow")
    diagram = view.get_by_role("group", name="Investigation swarms and agent handoffs")
    inspector = view.get_by_role("complementary", name="Agent inspector")
    nodes = diagram.get_by_role("button")
    expect(diagram).to_be_in_viewport()
    for group in ("Identity", "Discovery", "Challenge", "Decision"):
        expect(nodes.filter(has_text=f"{group} swarm").first).to_be_visible()
    if inspector.is_visible():
        inspector.get_by_role("button", name="Close inspector").click()
    expect(inspector).to_be_hidden()
    test_camera(page, view, diagram, mobile=mobile, reduced=reduced)
    control = "Play" if reduced else "Pause"
    expect(view.get_by_role("button", name=f"{control} data flow animation")).to_be_visible()
    expect(view.locator(".motion-control")).to_contain_text("Workflow map")
    frames = {diagram.screenshot()}
    for _ in range(3):
        page.wait_for_timeout(220)  # Sample the untouched map across browser paints.
        frames.add(diagram.screenshot())
    moved = len(frames) > 1
    assert moved == (not reduced), f"Unexpected map motion (reduced={reduced}, mobile={mobile})"

    node = diagram.get_by_role("button", name="Identity resolver agent", exact=True)
    if reduced and not mobile:
        view.get_by_role("button", name="Inspector", exact=True).focus()
        page.keyboard.press("Tab")
        expect(node).to_be_focused()
        assert node.locator("path").first.evaluate("p => getComputedStyle(p).strokeDasharray !== 'none'")
        page.keyboard.press("Enter")
    if mobile:
        node.tap()
    else:
        node.click()
    expect(diagram).not_to_be_focused()
    expect(diagram).to_have_css("outline-style", "none")
    expect(node).to_have_css("outline-style", "none")
    expect(inspector.get_by_role("heading", name="Assignment")).to_be_visible()
    expect(inspector.get_by_role("button", name=re.compile("^Identity resolver"), pressed=True)).to_be_visible()
    roster = page.request.get(url.split("#")[0].rstrip("/") + "/api/swarms/payment").json()["agents"]
    assert len(roster) == len({a["persona"] for a in roster}) == 36
    assert sum(bool(a["parent_id"]) for a in roster) == 24
    assert {n.get_attribute("data-agent-id") for n in nodes.all()} == {a["id"] for a in roster}
    specialist = next(a for a in roster if a["parent_id"] == "identity")
    specialist_node = diagram.locator('[data-agent-id="' + specialist["id"] + '"]')
    expect(specialist_node).to_have_count(1)
    if not mobile:
        specialist_node.focus()
        page.keyboard.press("Enter")
        expect(inspector.get_by_text(specialist["persona"], exact=True)).to_be_visible()
    if mobile:
        expect(inspector.get_by_role("button", name="Close inspector")).to_be_in_viewport()
        assert page.evaluate("innerWidth === 390 && document.documentElement.scrollWidth <= innerWidth"), "Mobile overflow"
    if not mobile and not reduced:
        check_live_intake(page, view, inspector, roster)
    page.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8080")
    parser.add_argument("--channel", default="chrome", help="Installed Chromium channel (default: chrome)")
    args = parser.parse_args()
    url = args.base_url.rstrip("/") + "/#swarm"
    expect.set_options(timeout=3500)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=args.channel)
        check_view(browser, url, mobile=True)
        check_view(browser, url, reduced=True)
        check_view(browser, url)
        browser.close()
    print("Swarm UI passed on mobile, reduced-motion desktop and animated desktop")
