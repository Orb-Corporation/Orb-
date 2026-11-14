'use strict';

const KEYWORDS = [
    ['fn', 'Function declaration'], ['struct', 'Struct declaration'], ['enum', 'Enum declaration'],
    ['const', 'Compile-time constant'], ['use', 'Import a module'], ['pub', 'Public declaration'],
    ['if', 'Conditional statement'], ['else', 'Alternative branch'], ['while', 'While loop'],
    ['for', 'Range, array, slice or string loop'], ['in', 'Loop iteration keyword'],
    ['loop', 'Infinite loop'], ['break', 'Exit the current loop'], ['continue', 'Continue the current loop'],
    ['return', 'Return from a function'], ['true', 'Boolean literal'], ['false', 'Boolean literal'],
    ['null', 'Null pointer literal'], ['as', 'Explicit type conversion'], ['try', 'Propagate an error'],
    ['catch', 'Handle an error'], ['extern', 'External function declaration'], ['error', 'Error declaration'],
    ['fail', 'Return an error']
];

const TYPES = ['i8','i16','i32','i64','u8','u16','u32','u64','f64','bool','str','never','error'];
const BUILTINS = [
    ['print', 'print(...)', 'Write values to standard output.'],
    ['println', 'println(...)', 'Write values followed by a newline.'],
    ['eprint', 'eprint(...)', 'Write values to standard error.'],
    ['eprintln', 'eprintln(...)', 'Write values followed by a newline to standard error.'],
    ['flush', 'flush()', 'Flush buffered standard output.'],
    ['free', 'free(value)', 'Release a pointer, slice or string returned by an allocating API.'],
    ['new', 'new(T)', 'Allocate a zero-initialised value of type T.'],
    ['make', 'make(T, count)', 'Allocate a zero-initialised slice.'],
    ['sizeof', 'sizeof(T)', 'Return the size of a type or value.'],
    ['panic', 'panic(message)', 'Print a panic message and terminate the program.'],
    ['assert', 'assert(condition, message)', 'Terminate when the condition is false.'],
    ['args', 'args()', 'Return the command-line arguments.']
];

const MODULES = {
    math: {
        description: 'Numeric helpers: constants, elementary functions, rounding and powers.',
        members: ['PI','E','sqrt','abs','min','max','clamp','floor','ceil','round','powi','ipow','sin','cos','exp','ln']
    },
    strings: {
        description: 'String helpers. Allocated return values must be released with free().',
        members: ['ParseError','concat','starts_with','ends_with','find','is_space','trim','parse_i64','from_i64']
    },
    io: {
        description: 'File and standard-input operations. Read results are allocated.',
        members: ['IoError','NotFound','read_file','write_file','read_stdin','read_line']
    },
    vec: {
        description: 'Generic growable arrays.',
        members: ['Vec','push','get','set','pop','count','items','slice_of','free_vec']
    },
    json: {
        description: 'Native and WebAssembly JSON parser with token-tree access.',
        members: ['InvalidJson','WrongType','NotFound','IndexOutOfRange','Kind','Token','Document','parse','free_doc','root','type_of','raw','string','count','at','get','number','boolean','is_null']
    },
    web: {
        description: 'Browser APIs available when compiling with --target wasm.',
        members: ['Element','Event','Response','Json','Listener','Timer','get_element','query','query_all','body','document','window','create','create_text','append','remove','clear','focus','get_text','set_text','get_html','set_html','get_attr','set_attr','remove_attr','has_attr','on_click','on_input','on_submit','fetch','set_timeout','set_interval','now','random','console','json_parse','json_get','json_at','json_string','json_number','json_bool','json_stringify']
    },
    os: {
        description: 'Low-level operating-system interface. Usually used by standard-library modules.',
        members: ['init','exit','read','write','open_read','open_write','close','alloc','release']
    }
};

const DOCS = new Map([
    ...BUILTINS.map(([name, signature, description]) => [name, `${signature}\n\n${description}`]),
    ...Object.entries(MODULES).map(([name, data]) => [name, data.description]),
    ['str', 'Immutable byte string represented by a pointer and a length. Use .ptr and .len to access its storage.'],
    ['[]T', 'Slice type: pointer plus length. Indexing is bounds-checked.'],
    ['T!', 'Error union: either a value of type T or an error. Use try, catch or fail.'],
    ['try', 'Propagate an error from the current function. The function must itself return an error union.'],
    ['catch', 'Handle an error with a fallback value or a diverging block.']
]);

function add(map, name, kind, detail, documentation, insertText = name) {
    if (!name || map.has(name)) return;
    map.set(name, { label: name, kind, detail: detail || '', documentation: documentation || '', insertText });
}

function localDeclarations(text) {
    const found = new Map();
    let m;
    const fnRe = /\b(?:pub\s+)?fn\s+([A-Za-z_]\w*)\s*(?:<[^>{}]*>)?\s*\(([^)]*)\)\s*(?:->\s*([^\{]+))?/g;
    while ((m = fnRe.exec(text))) {
        const args = (m[2] || '').replace(/\s+/g, ' ').trim();
        const ret = (m[3] || '').replace(/\s+/g, ' ').trim();
        add(found, m[1], 'Function', `fn ${m[1]}(${args})${ret ? ' -> ' + ret : ''}`, 'Declared in this file.');
        const paramRe = /(?:^|,)\s*([A-Za-z_]\w*)\s*:/g;
        let a;
        while ((a = paramRe.exec(args))) add(found, a[1], 'Variable', 'Function parameter', 'Parameter in the current file.');
    }
    const declRe = /\b(?:pub\s+)?(struct|enum|const|error)\s+([A-Za-z_]\w*)/g;
    while ((m = declRe.exec(text))) add(found, m[2], m[1] === 'const' ? 'Constant' : 'Class', m[1] + ' declaration', 'Declared in this file.');
    const variableRe = /(?:^|[;{}\n])\s*([A-Za-z_]\w*)\s*(?::=|:)\s*(?!=)/g;
    while ((m = variableRe.exec(text))) add(found, m[1], 'Variable', 'Variable in this file', 'Declared in this file.');
    return found;
}

function contextAt(text, offset) {
    const lineStart = text.lastIndexOf('\n', Math.max(0, offset - 1)) + 1;
    const before = text.slice(lineStart, offset);
    let m = /\buse\s+([A-Za-z_]\w*)?$/.exec(before);
    if (m) return { mode: 'module', prefix: m[1] || '' };
    m = /\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)?$/.exec(before);
    if (m) return { mode: 'member', module: m[1], prefix: m[2] || '' };
    m = /([A-Za-z_]\w*)$/.exec(before);
    return { mode: 'normal', prefix: m ? m[1] : '' };
}

function completions(text, offset) {
    const ctx = contextAt(text, offset);
    const out = new Map();
    if (ctx.mode === 'module') {
        for (const name of Object.keys(MODULES)) add(out, name, 'Module', 'Standard library module', MODULES[name].description);
    } else if (ctx.mode === 'member' && MODULES[ctx.module]) {
        for (const name of MODULES[ctx.module].members) add(out, name, 'Function', ctx.module + ' member', `Member of the ${ctx.module} module.`);
    } else {
        for (const [name, doc] of KEYWORDS) add(out, name, 'Keyword', 'Orb! keyword', doc);
        for (const name of TYPES) add(out, name, 'Class', 'Built-in type', `Built-in type ${name}.`);
        for (const [name, signature, description] of BUILTINS) add(out, name, 'Function', signature, description);
        for (const name of Object.keys(MODULES)) add(out, name, 'Module', 'Standard library module', MODULES[name].description);
        for (const [name, item] of localDeclarations(text)) add(out, name, item.kind, item.detail, item.documentation);
    }
    const prefix = ctx.prefix.toLowerCase();
    return [...out.values()].filter(x => x.label.toLowerCase().startsWith(prefix)).sort((a,b) => a.label.localeCompare(b.label));
}

function hover(text, offset, word) {
    const lineStart = text.lastIndexOf('\n', Math.max(0, offset - 1)) + 1;
    const before = text.slice(lineStart, offset);
    const member = /\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)$/.exec(before);
    if (member && MODULES[member[1]] && MODULES[member[1]].members.includes(member[2])) {
        return `**${member[1]}.${member[2]}**\n\nStandard-library member of \`${member[1]}\`.`;
    }
    if (DOCS.has(word)) return DOCS.get(word);
    const escaped = word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const re = new RegExp(`\\b(?:pub\\s+)?fn\\s+${escaped}\\s*(?:<[^>{}]*>)?\\s*\\(([^)]*)\\)\\s*(?:->\\s*([^\\{]+))?`);
    const m = re.exec(text);
    if (m) return `\`fn ${word}(${m[1].replace(/\s+/g, ' ').trim()})${m[2] ? ' -> ' + m[2].trim() : ''}\`\n\nDeclared in this file.`;
    return null;
}

module.exports = { completions, hover, localDeclarations, contextAt };
