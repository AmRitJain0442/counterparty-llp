"""Check /#swarm on a running app. Files one Payment demo after the read-only checks.

    python scripts/swarm_smoke.py [BASE_URL] --channel chrome
"""
import argparse
import json
import re

from playwright.sync_api import expect, sync_playwright


def run_demo(page, inspector, agent_ids):
    inspector.get_by_role("button", name="Run", exact=True).click()
    expect(inspector.get_by_role("radio", name="Demo")).to_be_checked()

    # All other API writes stay blocked, including a duplicate submission.
    def allow_demo(route):
        req = route.request
        if req.method == "POST" and (req.post_data_json or {}).get("mode") == "demo":
            route.continue_()
        else:
            route.abort()

    page.route("**/api/cases/stream", allow_demo, times=1)
    with page.expect_request_finished(lambda r: r.url.endswith("/api/cases/stream"), timeout=8000) as filed:
        inspector.get_by_role("button", name="Run the Payment demo", exact=True).click()
    response = filed.value.response()
    assert response.ok, f"Demo returned HTTP {response.status}"
    messages = [json.loads(line) for line in response.text().splitlines() if line.strip()]
    assert messages[-1]["type"] == "case", "Demo stream did not end with a filed case"
    case = messages[-1]["case"]
    events = [m for m in messages if m.get("agent_id")]
    assert case["mode"] == "demo" and events == case["swarm_events"], "Filed trace differs from demo stream"
    phases = {}
    expected = [("start", "running"), ("end", "complete")]
    for event in events:
        agent = event["agent_id"]
        for dep in event["depends_on"]:
            assert phases.get(dep) == expected, f"{agent} ran before {dep} finished"
        phases.setdefault(agent, []).append((event["event"], event["status"]))
    assert phases.keys() == agent_ids, "Streamed agents differ from map nodes"
    for agent, sequence in phases.items():
        assert sequence == expected, f"{agent} emitted {sequence}"

    agent_count = len(agent_ids)
    expect(inspector.get_by_text(case["receipt"][:16], exact=True)).to_be_visible()
    expect(inspector.get_by_text(f"Synthetic investigation · {agent_count} of {agent_count} agent reports",
                                 exact=True)).to_be_visible(timeout=8000)
    # Recent activity presents the last handoff newest first.
    activity = inspector.get_by_role("button", name=re.compile("^" + re.escape(events[-1]["name"])))
    expect(activity).to_have_text([re.compile("Done"), re.compile("Running")])
    return len(events)


def check_view(browser, url, *, mobile=False, reduced=False):
    page = browser.new_page(viewport={"width": 390 if mobile else 1440, "height": 844 if mobile else 900},
                            is_mobile=mobile, has_touch=mobile, reduced_motion="reduce" if reduced else "no-preference")
    page.set_default_timeout(3500)
    page.route("**/api/**", lambda r: r.continue_() if r.request.method == "GET" else r.abort())
    page.goto(url, wait_until="domcontentloaded", timeout=8000)
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
    control = "Play" if reduced else "Pause"
    expect(view.get_by_role("button", name=f"{control} data flow animation")).to_be_visible()
    frames = {diagram.screenshot()}
    for _ in range(3):
        page.wait_for_timeout(220)  # Sample the untouched map across browser paints.
        frames.add(diagram.screenshot())
    moved = len(frames) > 1
    assert moved == (not reduced), f"Unexpected map motion (reduced={reduced}, mobile={mobile})"

    node = diagram.get_by_role("button", name="Identity resolver agent", exact=True)
    if mobile:
        node.tap()
    else:
        node.click()
    expect(inspector.get_by_role("heading", name="Assignment")).to_be_visible()
    expect(inspector.get_by_role("button", name=re.compile("^Identity resolver"), pressed=True)).to_be_visible()
    if mobile:
        expect(inspector.get_by_role("button", name="Close inspector")).to_be_in_viewport()
        assert page.evaluate("innerWidth === 390 && document.documentElement.scrollWidth <= innerWidth"), "Mobile overflow"
    if not mobile and not reduced:
        agent_ids = {node.get_attribute("data-agent-id") for node in nodes.all()}
        events = run_demo(page, inspector, agent_ids)
        print(f"Payment demo filed with {events} ordered agent events")
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
