//! `--selftest` (short walk, no run) and `--selftest-campaign` (the fake campaign to its end, then the delete side):
//! the core walks the screens by itself and records what the window shows, so the real window can be
//! checked without a person. Only on that command-line flag; the window cannot turn it on. The steps are fixed
//! here; each `shot` line in the log is where packaging/selftest-window.ps1 takes a picture of the window. The
//! script also gives the verdict: it fails unless this run's log shows the refusal, the campaign accepted, the run
//! started with stream lines and stopped, and every screen's data command answered (so a walk whose form the
//! engine refused cannot pass). A field the form requires must be typed in the step below.

use std::time::Duration;

use tauri::{AppHandle, Manager};

// The walks save no key: the real engine writes into the real keyring of the account (packaging/selftest-window.ps1
// does the guarded key proof outside the walk when the engine has a keyring at all).

/// Injected before the page's own scripts (self-test only): records content-security-policy violations, errors,
/// unhandled rejections and console errors, and gives the steps a few plain helpers.
pub const PROBE: &str = r#"(function () {
  if (window.__lfProbe) return;
  var p = (window.__lfProbe = { violations: [], errors: [] });
  document.addEventListener('securitypolicyviolation', function (e) {
    p.violations.push(e.violatedDirective + ' ' + (e.blockedURI || ''));
  });
  window.addEventListener('error', function (e) { p.errors.push('error: ' + (e.message || '')); });
  window.addEventListener('unhandledrejection', function (e) {
    var r = e.reason; p.errors.push('rejection: ' + String((r && r.message) || r));
  });
  var ce = console.error.bind(console);
  console.error = function () {
    p.errors.push('console.error: ' + Array.prototype.map.call(arguments, String).join(' ').slice(0, 300));
    ce.apply(null, arguments);
  };
  window.__lf = {
    rail: function (i) { var b = document.querySelectorAll('.ds-rail__item')[i]; if (b) b.click(); return !!b; },
    button: function (t) {
      var b = Array.prototype.find.call(document.querySelectorAll('main button'), function (x) {
        return x.textContent.trim().indexOf(t) === 0 && !x.disabled;
      });
      if (b) b.click(); return !!b;
    },
    dialog: function (t) {
      var b = Array.prototype.find.call(document.querySelectorAll('dialog[open] button'), function (x) {
        return x.textContent.trim().indexOf(t) === 0 && !x.disabled;
      });
      if (b) b.click(); return !!b;
    },
    label: function (l) {
      var b = document.querySelector('main button[aria-label="' + l + '"]');
      if (b && !b.disabled) { b.click(); return true; } return false;
    },
    has: function (t) { var m = document.querySelector('main'); return !!m && m.innerText.indexOf(t) >= 0; },
    type: function (sel, v) {
      var el = document.querySelector(sel); if (!el) return false;
      var proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
      el.dispatchEvent(new Event('input', { bubbles: true })); return true;
    },
    text: function () {
      var m = document.querySelector('main');
      return (m ? m.getAttribute('data-screen') + ' | ' + m.innerText : '(no main)').replace(/\s+/g, ' ').slice(0, 600);
    },
  };
})();"#;

enum Step {
    Js(&'static str, String),
    Wait(u64),
    Shot(&'static str),
    /// Ask the page every second until the script answers `true`, at most this long; a line every 10 s keeps the
    /// script's 20 s step bound from firing while a run goes on.
    Until(&'static str, &'static str, u64),
}

/// Which walk: `--selftest` is the short walk (no run: the installed app's, whose bundled engine cannot load the
/// fakes' harness), `--selftest-campaign` the whole fake campaign (debug build, fakes started by the script).
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Walk {
    Short,
    Campaign,
}

impl Walk {
    pub fn from_args(args: &[String]) -> Option<Self> {
        if args.iter().any(|a| a == "--selftest-campaign") {
            Some(Walk::Campaign)
        } else if args.iter().any(|a| a == "--selftest") {
            Some(Walk::Short)
        } else {
            None
        }
    }

    /// The whole walk's bound: past it the app ends itself with exit code 1 (packaging/selftest-window.ps1 also stops
    /// the app at this bound, and when 20 s pass with no step of the walk in the log).
    pub fn bound(self) -> Duration {
        match self {
            Walk::Short => Duration::from_secs(120),
            Walk::Campaign => Duration::from_secs(420),
        }
    }
}

/// The form, typed as a person would: kind, place, offer (and the cap for the campaign walk).
fn fill(kind: &str, place: &str, cap: Option<&str>) -> String {
    let mut js = format!(
        "__lf.type('main input[placeholder=\"MOT garage\"]','{kind}'); __lf.type('main input[placeholder=\"Bristol\"]','{place}'); __lf.type('main textarea','Online booking for independent garages')"
    );
    if let Some(c) = cap {
        js.push_str(&format!(
            "; __lf.type('main input[inputmode=\"numeric\"]','{c}')"
        ));
    }
    js
}

fn start_steps() -> Vec<Step> {
    use Step::*;
    vec![
        Wait(4000),
        Shot("01-campaign"),
        Js(
            "submit the empty form (the engine answers with its error document)",
            "__lf.button('Check the plan')".into(),
        ),
        Wait(3000),
        Shot("02-campaign-error"),
    ]
}

fn steps(walk: Walk) -> Vec<Step> {
    use Step::*;
    let mut s = start_steps();
    match walk {
        Walk::Short => s.extend([
            Js(
                "fill kind, place and offer",
                fill("car repair", "Bristol", None),
            ),
            Wait(400),
            Js("check the plan", "__lf.button('Check the plan')".into()),
            Wait(3000),
            Shot("03-campaign-plan"),
            Js("rail: results", "__lf.rail(2)".into()),
            Wait(2500),
            Shot("06-results"),
            Js("rail: people", "__lf.rail(3)".into()),
            Wait(2500),
            Shot("07-people"),
            Js("rail: data", "__lf.rail(4)".into()),
            Wait(3000),
            Shot("08-data"),
            Js("rail: keys", "__lf.rail(5)".into()),
            Wait(2500),
            Shot("09-keys"),
            Js("rail: settings", "__lf.rail(6)".into()),
            Wait(2500),
            Shot("10-settings"),
        ]),
        Walk::Campaign => {
            s.extend([
                Js("fill kind, place, offer and the cap", fill("car repair", "Bristol", Some("50"))),
                Wait(400),
                Js("check the plan", "__lf.button('Check the plan')".into()),
                Wait(3000),
                Shot("03-campaign-plan"),
                Js("start the run", "__lf.button('Start the run')".into()),
                Wait(3000),
                Shot("04-run-streaming"),
                Until("the run finishes", "__lf.has('Open the results')", 300_000),
                Shot("05-run-finished"),
                Js("open the results", "__lf.button('Open the results')".into()),
                Wait(3000),
                Js("write the sheet again (sheet_export)", "__lf.button('Write it again')".into()),
                Until("the sheet is written", "!__lf.has('Writing')", 60_000),
                Wait(1500),
                Shot("06-results-exported"),
                Js("rail: people", "__lf.rail(3)".into()),
                Wait(3000),
                Shot("07-people"),
                // a domain: forget removes every record of that business (Ysolde Fenwick, Millbrook Autos) and its lines in
                // the exports; the fake campaign's sheet holds no person's email address to forget instead
                Js("type the domain to forget", "__lf.type('main input[placeholder=\"name@business.example\"]','millbrook-autos.example')".into()),
                Wait(400),
                Js("forget: open the confirmation", "__lf.button('Forget')".into()),
                Wait(800),
                Js("forget: confirm", "__lf.dialog('Delete and keep them out')".into()),
                Until("the forget is done", "!document.querySelector('dialog[open]')", 60_000),
                Wait(2500),
                Shot("07b-people-forgotten"),
                Js("type the domain to suppress", "__lf.type('main input[placeholder=\"name@business.example\"]','kestrel-garage.example')".into()),
                Wait(400),
                Js("suppress: open the confirmation", "__lf.button('Suppress')".into()),
                Wait(800),
                Js("suppress: confirm", "__lf.dialog('Suppress')".into()),
                Until("the suppress is done", "!document.querySelector('dialog[open]')", 60_000),
                Wait(2500),
                Shot("07c-people-suppressed"),
                Js("rail: data", "__lf.rail(4)".into()),
                Wait(3500),
                Shot("08-data"),
            ]);
            for _ in 0..11 {
                s.push(Js(
                    "retention: one month less",
                    "__lf.label('One month less')".into(),
                ));
                s.push(Wait(250));
            }
            s.extend([
                Js(
                    "retention: save the shorter period",
                    "__lf.button('Save 1 month')".into(),
                ),
                Wait(4000),
                Shot("08b-data-retention-1-month"),
                Js(
                    "purge: open the confirmation if anything is past the limit",
                    "__lf.button('Delete the')".into(),
                ),
                Wait(800),
                Js("purge: confirm", "__lf.dialog('Delete them')".into()),
                Wait(4000),
                Shot("08c-data-purge"),
                Js("rail: keys", "__lf.rail(5)".into()),
                Wait(3000),
                Shot("09-keys"),
                Js("rail: settings", "__lf.rail(6)".into()),
                Wait(2500),
                Shot("10-settings"),
            ]);
        }
    }
    s
}

/// Walks the steps on its own thread, then reports the probe and exits.
pub fn start(app: AppHandle, walk: Walk) {
    let guard = app.clone();
    std::thread::spawn(move || {
        std::thread::sleep(walk.bound());
        crate::core_log(
            &guard,
            &format!(
                "selftest: the walk passed its {} s bound; the app ends itself",
                walk.bound().as_secs()
            ),
        );
        guard.exit(1);
    });
    std::thread::spawn(move || {
        let log = |m: &str| crate::core_log(&app, m);
        let Some(w) = app.get_webview_window("main") else {
            log("selftest: no main window");
            app.exit(1);
            return;
        };
        log(&format!("selftest: walk {walk:?}"));
        for step in steps(walk) {
            match step {
                Step::Wait(ms) => std::thread::sleep(Duration::from_millis(ms)),
                Step::Until(what, js, max_ms) => {
                    log(&format!("selftest: waiting until {what}"));
                    let t0 = std::time::Instant::now();
                    let mut said = t0;
                    loop {
                        let (tx, rx) = std::sync::mpsc::channel();
                        let _ = w.eval_with_callback(js, move |r| {
                            let _ = tx.send(r);
                        });
                        if rx.recv_timeout(Duration::from_secs(3)).as_deref() == Ok("true") {
                            log(&format!(
                                "selftest: {what}: yes after {} s",
                                t0.elapsed().as_secs()
                            ));
                            break;
                        }
                        if t0.elapsed() > Duration::from_millis(max_ms) {
                            log(&format!("selftest: {what}: NOT within {} s", max_ms / 1000));
                            break;
                        }
                        if said.elapsed() > Duration::from_secs(10) {
                            said = std::time::Instant::now();
                            log(&format!("selftest: still waiting until {what}"));
                        }
                        std::thread::sleep(Duration::from_secs(1));
                    }
                }
                Step::Js(what, js) => {
                    // the step's text is logged, never the script (one step carries the marker key)
                    log(&format!("selftest: {what}"));
                    let _ = w.eval(js);
                }
                Step::Shot(name) => {
                    let a = app.clone();
                    let _ = w.eval_with_callback("__lf.text()", move |text| {
                        crate::core_log(&a, &format!("selftest: shows {name}: {text}"));
                    });
                    std::thread::sleep(Duration::from_millis(400));
                    log(&format!("selftest: shot {name}"));
                    std::thread::sleep(Duration::from_millis(900));
                }
            }
        }
        let a = app.clone();
        let _ = w.eval_with_callback("JSON.stringify(window.__lfProbe)", move |probe| {
            crate::core_log(&a, &format!("selftest: probe {probe}"));
        });
        std::thread::sleep(Duration::from_millis(1000));
        log("selftest: done");
        app.exit(0);
    });
}
