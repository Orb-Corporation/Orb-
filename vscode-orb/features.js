'use strict';

// Small, dependency-free editor intelligence for Orb!. This intentionally uses a
// conservative lexical index instead of pretending to be a full semantic LSP.
const KEYWORDS = [
  'fn','pub','struct','enum','const','use','if','else','while','for','in','loop',
  'break','continue','return','true','false','null','as','try','catch','extern',
  'error','fail'
];
const BUILTINS = {
  print: 'print(...): write values to standard output.',
  println: 'println(...): write values followed by a newline.',
  eprint: 'eprint(...): write values to standard error.',
  eprintln: 'eprintln(...): write values followed by a newline to standard error.',
  flush: 'flush(): flush buffered standard output.',
  exit: 'exit(code: i64): terminate the process.',
  panic: 'panic(message: str): report a runtime failure and terminate.',
  assert: 'assert(condition: bool, message: str): panic when the condition is false.',
  args: 'args() -> []str: return command-line arguments.',
  mem_alloc: 'mem_alloc(size: i64) -> *u8: allocate raw memory.',
  mem_zalloc: 'mem_zalloc(size: i64) -> *u8: allocate zeroed memory.',
  new: 'new(T): allocate a zero-initialized value.',
  make: 'make(T, count): allocate a zero-initialized slice.',
  free: 'free(pointer): release allocated memory.'
};
const MODULES = {
  math: {
    detail: 'Standard numeric helpers.',
    members: ['PI','E','sqrt','abs','min','max','clamp','floor','ceil','round','powi','ipow','sin','cos','exp','ln']
  },
  strings: {
    detail: 'String helpers. Strings are immutable byte slices.',
    members: ['concat','starts_with','ends_with','find','is_space','trim','parse_i64','from_i64']
  },
  io: {
    detail: 'File and standard-input operations.',
    members: ['read_file','write_file','read_stdin','read_line','IoError','NotFound']
  },
  vec: {
    detail: 'Generic growable arrays.',
    members: ['Vec','push','get','set','pop','count','items','free_vec']
  },
  json: {
    detail: 'JSON validation and string encoding.',
    members: ['validate','quote']
  },
  web: {
    detail: 'Browser APIs available for the WebAssembly target.',
    members: ['log','set_text','get_value','set_value','on_click','on_input','fetch']
  }
};
const KEYWORD_DOCS = {
  use: 'use module; imports a module from the current source directory or the embedded standard library.',
  pub: 'pub marks a module declaration as accessible to importing modules.',
  try: 'try propagates an error from an error-union expression.',
  catch: 'catch handles an error-union expression.',
  fail: 'fail returns an error from a function with an error-union return type.',
  defer: 'defer is not a supported Orb! keyword in this compiler version.'
};

function declarations(text) {
  const found = [];
  const re = /\b(?:pub\s+)?(fn|struct|enum|error|const)\s+([A-Za-z_][A-Za-z0-9_]*)/g;
  let match;
  while ((match = re.exec(text))) {
    found.push({ label: match[2], kind: match[1], detail: match[1] + ' declaration' });
  }
  const vars = /(?:^|[;{}\n])\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?::=|:\s*[A-Za-z_][A-Za-z0-9_<>,*\[\]!]*\s*=)/g;
  while ((match = vars.exec(text))) found.push({ label: match[1], kind: 'variable', detail: 'Local or global variable' });
  return found;
}

function complete(text, offset) {
  const before = String(text).slice(0, Math.max(0, offset));
  const member = /([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)?$/.exec(before);
  let candidates = [];
  let prefix = '';
  if (member && MODULES[member[1]]) {
    prefix = member[2] || '';
    candidates = MODULES[member[1]].members.map(label => ({
      label, kind: 'function', detail: member[1] + ' module member'
    }));
  } else {
    const keywordItems = KEYWORDS.map(label => ({ label, kind: 'keyword', detail: 'Orb! keyword' }));
    const builtinItems = Object.entries(BUILTINS).map(([label, documentation]) => ({
      label, kind: 'function', detail: 'Built-in', documentation
    }));
    const moduleItems = Object.entries(MODULES).map(([label, info]) => ({
      label, kind: 'module', detail: info.detail, documentation: info.detail
    }));
    candidates = [...keywordItems, ...builtinItems, ...moduleItems, ...declarations(String(text))];
    const word = /[A-Za-z_][A-Za-z0-9_]*$/.exec(before);
    prefix = word ? word[0] : '';
  }
  const seen = new Set();
  return candidates.filter(item => {
    if (!item.label.startsWith(prefix) || seen.has(item.label)) return false;
    seen.add(item.label);
    return true;
  }).sort((a,b) => a.label.localeCompare(b.label));
}

function wordAt(text, offset) {
  const source = String(text);
  const i = Math.max(0, Math.min(offset, source.length));
  const left = /[A-Za-z_][A-Za-z0-9_]*$/.exec(source.slice(0, i));
  const right = /^[A-Za-z0-9_]*/.exec(source.slice(i));
  return (left ? left[0] : '') + (right ? right[0] : '');
}

function hover(text, offset) {
  const source = String(text);
  const name = wordAt(source, offset);
  if (!name) return null;
  if (BUILTINS[name]) return BUILTINS[name];
  if (MODULES[name]) return 'module ' + name + ' — ' + MODULES[name].detail;
  if (KEYWORD_DOCS[name]) return KEYWORD_DOCS[name];
  const left = source.slice(0, offset);
  const moduleMatch = /([A-Za-z_][A-Za-z0-9_]*)\.$/.exec(left);
  if (moduleMatch && MODULES[moduleMatch[1]] && MODULES[moduleMatch[1]].members.includes(name)) {
    const module = moduleMatch[1];
    const signature = new RegExp('\\b(?:pub\\s+)?fn\\s+' + name + '\\s*\\(([^)]*)\\)(?:\\s*->\\s*([^\\{]+))?').exec(source);
    return signature
      ? module + '.' + name + '(' + signature[1] + ')' + (signature[2] ? ' -> ' + signature[2].trim() : '')
      : module + '.' + name + ' — standard-library member';
  }
  const decl = new RegExp('\\b(?:pub\\s+)?fn\\s+' + name + '\\s*\\(([^)]*)\\)(?:\\s*->\\s*([^\\{]+))?').exec(source);
  if (decl) return 'fn ' + name + '(' + decl[1] + ')' + (decl[2] ? ' -> ' + decl[2].trim() : '');
  return null;
}

function signature(text, offset) {
  const source = String(text);
  const end = Math.max(0, Math.min(offset, source.length));
  let depth = 0, open = -1, inString = false, escaped = false;
  for (let i = end - 1; i >= 0; i--) {
    const ch = source[i];
    if (ch === '"' && !escaped) inString = !inString;
    if (inString) { escaped = ch === '\\' && !escaped; continue; }
    if (ch === ')') depth++;
    else if (ch === '(') {
      if (depth === 0) { open = i; break; }
      depth--;
    }
    escaped = ch === '\\' && !escaped;
  }
  if (open < 0) return null;
  const call = /([A-Za-z_][A-Za-z0-9_]*)\s*$/.exec(source.slice(0, open));
  if (!call) return null;
  const name = call[1];
  let params = null, result = '';
  const modulePrefix = /([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*$/.exec(source.slice(0, call.index));
  if (modulePrefix && MODULES[modulePrefix[1]]) {
    const standard = {
      math: { sqrt: ['x: f64'], abs: ['x: T'], min: ['a: T','b: T'], max: ['a: T','b: T'], clamp: ['x: T','lo: T','hi: T'], powi: ['x: f64','n: i64'], ipow: ['base: i64','exp: i64'] },
      strings: { concat: ['a: str','b: str'], find: ['s: str','needle: str'], parse_i64: ['s: str'] },
      io: { read_file: ['path: str'], write_file: ['path: str','data: str'], read_line: [] },
      json: { validate: ['source: str'], quote: ['source: str'] },
      web: { set_text: ['id: str','value: str'], get_value: ['id: str'], fetch: ['url: str'] }
    };
    params = standard[modulePrefix[1]] && standard[modulePrefix[1]][name];
  }
  const re = new RegExp('\\b(?:pub\\s+)?fn\\s+' + name + '\\s*\\(([^)]*)\\)(?:\\s*->\\s*([^\\{]+))?');
  const decl = re.exec(source);
  if (!params && decl) {
    params = decl[1].trim() ? decl[1].split(',').map(p => p.trim()) : [];
    result = decl[2] ? ' -> ' + decl[2].trim() : '';
  }
  if (!params && BUILTINS[name]) {
    const builtins = { println: ['...values'], print: ['...values'], assert: ['condition: bool','message: str'], panic: ['message: str'], exit: ['code: i64'], free: ['pointer: *T'] };
    params = builtins[name];
  }
  if (!params) return null;
  const argsText = source.slice(open + 1, end);
  let active = 0, nested = 0;
  for (const ch of argsText) {
    if (ch === '(' || ch === '[' || ch === '{') nested++;
    else if (ch === ')' || ch === ']' || ch === '}') nested = Math.max(0, nested - 1);
    else if (ch === ',' && nested === 0) active++;
  }
  const label = name + '(' + params.join(', ') + ')' + result;
  return { label, parameters: params, activeParameter: Math.min(active, Math.max(0, params.length - 1)) };
}

module.exports = { complete, hover, signature, MODULES, BUILTINS, KEYWORDS };
