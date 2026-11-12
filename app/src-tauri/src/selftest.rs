//! `--selftest`: the core walks the screens by itself and records what the window shows, so the real window can be
//! checked without a person. Only on that command-line flag; the window cannot turn it on. The steps are fixed
//! here; each `shot` line in the log is where packaging/selftest-window.ps1 takes a picture of the window. The
//! script also gives the verdict: it fails unless this run's log shows the refusal, the campaign accepted, the run
//! started with stream lines and stopped, and every screen's data command answered (so a walk whose form the
//! engine refused cannot pass). A field the form requires must be typed in the step below.

use std::time::Duration;

use tauri::{AppHandle, Manager};

/// A made-up key value the self-test types into the Keys screen. The proof searches every output for it.
pub const KEY_MARKER: &str = "LF-SELFTEST-KEY-7f3a9c51";

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
        return x.textContent.trim().indexOf(t) === 0;
      });
      if (b) b.click(); return !!b;
    },
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
}

fn steps() -> Vec<Step> {
    use Step::*;
    vec![
        Wait(4000),
        Shot("01-campaign"),
        Js("submit the empty form (the stand-in answers with an error object)", "__lf.button('Check the plan')".into()),
        Wait(1600),
        Shot("02-campaign-error"),
        Js("fill kind, place and offer", "__lf.type('main input[placeholder=\"MOT garage\"]','MOT garage'); __lf.type('main input[placeholder=\"Bristol\"]','Bristol'); __lf.type('main textarea','Online booking for MOT tests')".into()),
        Wait(400),
        Js("check the plan", "__lf.button('Check the plan')".into()),
        Wait(1600),
        Shot("03-campaign-plan"),
        Js("start the run", "__lf.button('Start the run')".into()),
        Wait(3000),
        Shot("04-run-streaming"),
        Js("stop the run", "__lf.button('Stop')".into()),
        Wait(2500),
        Shot("05-run-stopped"),
        // a start the engine refuses: the stand-in's case `standin-refuse` (the plan names the campaign
        // "standin-refuse-mot-garages"); line 1 is its error document, and the screen shows "start refused"
        Js("rail: campaign", "__lf.rail(0)".into()),
        Wait(1200),
        Js("fill a campaign the engine refuses to start", "__lf.type('main input[placeholder=\"MOT garage\"]','MOT garage'); __lf.type('main input[placeholder=\"Bristol\"]','Standin refuse'); __lf.type('main textarea','Online booking for MOT tests')".into()),
        Wait(400),
        Js("check the plan", "__lf.button('Check the plan')".into()),
        Wait(1600),
        Js("start the run the engine refuses", "__lf.button('Start the run')".into()),
        Wait(2500),
        Shot("05b-run-refused"),
        Js("rail: results", "__lf.rail(2)".into()),
        Wait(1600),
        Shot("06-results"),
        Js("rail: people", "__lf.rail(3)".into()),
        Wait(1600),
        Shot("07-people"),
        Js("rail: data", "__lf.rail(4)".into()),
        Wait(1600),
        Shot("08-data"),
        Js("rail: keys", "__lf.rail(5)".into()),
        Wait(1600),
        // a key already saved in this workspace shows "Replace" instead of the field (a second walk finds that)
        Js("open the key field if a key is already saved", "__lf.button('Replace')".into()),
        Wait(500),
        Js("type the marker key and save it",format!("__lf.type('main input','{KEY_MARKER}')")),
        Wait(500),
        Js("save the key", "__lf.button('Save in the keyring')".into()),
        Wait(1600),
        Shot("09-keys"),
        Js("rail: settings", "__lf.rail(6)".into()),
        Wait(1600),
        Shot("10-settings"),
    ]
}

/// The whole walk's bound: past it the app ends itself with exit code 1 (packaging/selftest-window.ps1 also
/// stops the app at this bound, and when 20 s pass with no step of the walk in the log).
pub const WALK_BOUND: Duration = Duration::from_secs(120);

/// Walks the steps on its own thread, then reports the probe and exits.
pub fn start(app: AppHandle) {
    let guard = app.clone();
    std::thread::spawn(move || {
        std::thread::sleep(WALK_BOUND);
        crate::core_log(
            &guard,
            "selftest: the walk passed its 120 s bound; the app ends itself",
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
        for step in steps() {
            match step {
                Step::Wait(ms) => std::thread::sleep(Duration::from_millis(ms)),
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
