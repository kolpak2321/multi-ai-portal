import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {parseHTML} from 'linkedom';
const extract=Function('return ('+readFileSync(new URL('../answer_markdown.js',import.meta.url),'utf8')+')')();
function convert(html){return extract(parseHTML('<div id="answer">'+html+'</div>').document.querySelector('#answer'));}
test('DeepSeek citation keeps source link and drops invisible dash',()=>{
 const md=convert('<p>В Европе <strong>44 страны</strong><a href="https://example.org/#1"><span class="ds-markdown-cite"><span style="opacity:0">-</span><span>3</span></span></a>.</p><h3>Уточнения</h3><ul><li><p><strong>50 стран</strong>: другой подсчёт.</p></li></ul>');
 assert.match(md,/\*\*44 страны\*\* \[3\]\(https:\/\/example.org\/#1\)\./);
 assert.match(md,/### Уточнения/);assert.match(md,/- \*\*50 стран\*\*/);assert.doesNotMatch(md,/-\n3/);
});
test('Z.ai ignores reasoning and keeps nested lists, tables and code',()=>{
 const md=convert('<div class="thinking-chain-container"><p>Private reasoning</p></div><p>Ответ</p><ol start="2"><li>A<ul><li>B</li></ul></li></ol><table><tr><th>Имя</th><th>Число</th></tr><tr><td>X</td><td>2</td></tr></table><pre><code class="language-python">x = 1\nprint(x)</code></pre>');
 assert.doesNotMatch(md,/reasoning/);assert.match(md,/2\. A\n  - B/);assert.match(md,/\| Имя \| Число \|\n\| --- \| --- \|/);assert.match(md,/```python\nx = 1\nprint\(x\)\n```/);
});
test('untrusted HTML and unsafe URLs never become executable markup',()=>{
 const md=convert('<script>secret()</script><p><a href="javascript:alert(1)">click</a> &lt;img onerror=evil&gt;</p><button>Copy</button>');
 assert.doesNotMatch(md,/javascript:|secret\(\)|Copy/);assert.match(md,/\\<img/);
});
