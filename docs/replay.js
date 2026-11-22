const get = id => document.getElementById(id);

function make(tag, className, text = '') {
  const element = document.createElement(tag);
  element.className = className;
  element.textContent = text;
  return element;
}

async function initialize() {
  const response = await fetch('events.json');
  if (!response.ok) throw new Error('Trace unavailable');
  const {base, fix} = await response.json();
  const end = base.at(-1).at;
  const deadline = fix.at(-1).at;
  const format = seconds => `${seconds} s`;
  const count = (events, clock) => events.filter(e => e.kind === 'request' && e.at <= clock).length;
  get('axis-mid').textContent = format(end / 2);
  get('axis-end').textContent = format(end);
  const renderers = [];
  for (const [label, color, events] of [['Before fix', '#ff9b76', base], ['After fix', '#bbd99f', fix]]) {
    const trace = make('section', 'trace');
    trace.style.setProperty('--trace', color);
    const title = make('div', 'trace-title', label);
    const state = make('span', 'small');
    title.append(state);
    const bar = make('div', 'bar');
    const fill = make('div', 'fill');
    const rule = make('i', 'deadline');
    rule.style.left = `${deadline / end * 100}%`;
    bar.append(fill, rule);
    const markers = events.filter(e => e.kind === 'request').map(e => {
      const dot = make('i', 'marker');
      dot.title = 'Status request at ' + format(e.at);
      dot.style.left = `${e.at / end * 100}%`;
      bar.append(dot);
      return [dot, e.at];
    });
    trace.append(title, bar);
    get('tracks').append(trace);
    const last = events.at(-1);
    renderers.push(clock => {
      fill.style.width = `${Math.min(clock, last.at) / end * 100}%`;
      for (const [dot, at] of markers) dot.hidden = at > clock;
      const requests = count(events, clock);
      state.textContent = (clock >= last.at ? format(last.at) + ' · ' : '') + requests + (requests === 1 ? ' request' : ' requests');
    });
  }
  const paint = clock => {
    for (const render of renderers) render(clock);
    get('clock').textContent = clock.toFixed(1) + ' s';
  };
  paint(end);
  get('assertion').textContent = "assert (outcome, now, sum(e['kind'] == 'request' for e in events)) == ('timeout', 1, 1)";
  get('explanation').textContent = `Before the fix the SDK reported completion after ${end} simulated seconds and ${count(base,end)} requests. The fix timed out after ${deadline} simulated second and ${count(fix,end)} request.`;
  const verdict = 'Reproduced before, passed after.';
  get('verdict').textContent = verdict;
  const button = get('replay');
  button.disabled = false;
  let frame;
  button.addEventListener('click', () => {
    cancelAnimationFrame(frame);
    button.textContent = 'Restart replay';
    const start = performance.now();
    const duration = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 5000;
    get('verdict').textContent = 'Replaying the recorded test…';
    const tick = now => {
      const clock = duration ? Math.min(end, (now - start) / duration * end) : end;
      paint(clock);
      if (clock < end) frame = requestAnimationFrame(tick);
      else {
        button.textContent = 'Replay again';
        get('verdict').textContent = verdict;
      }
    };
    frame = requestAnimationFrame(tick);
  });
}
initialize().catch(() => {
  get('verdict').textContent = 'The trace could not load. Open the run report for the recorded output.';
});
