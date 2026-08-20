import assert from 'node:assert/strict';
import test from 'node:test';

import {
    buildSelectedTextFormattingSegments,
    findPreservedLineBreakOffsetsInText,
    removeInlineFormattingFromTextSegments,
} from '../../app/static/js/modules/mode-manager/services/selected-formatting-removal-service.js';


test('selected formatting removal records CSS-rendered newlines as text offsets', () => {
    assert.deepEqual(
        findPreservedLineBreakOffsetsInText({
            text: 'First paragraph\n\nSecond paragraph',
            textStart: 12,
            selectionStart: 12,
            selectionEnd: 45,
        }),
        [27, 28],
    );
});


test('selected formatting removal records only fully selected newline sequences', () => {
    assert.deepEqual(
        findPreservedLineBreakOffsetsInText({
            text: 'alpha\r\nbeta\ngamma',
            textStart: 5,
            selectionStart: 7,
            selectionEnd: 17,
        }),
        [10, 16],
    );
});


test('selected formatting removal splits a multi-paragraph selection by text node', () => {
    assert.deepEqual(
        buildSelectedTextFormattingSegments({
            textNodeLengths: [38, 21, 164, 104],
            selectionStart: 0,
            selectionEnd: 327,
        }),
        [
            { start: 0, end: 38 },
            { start: 38, end: 59 },
            { start: 59, end: 223 },
            { start: 223, end: 327 },
        ],
    );
});


test('inline formatting removal preserves paragraph containers', () => {
    const originalDocument = globalThis.document;
    const originalHTMLElement = globalThis.HTMLElement;
    const originalNodeFilter = globalThis.NodeFilter;

    class FakeNode {
        constructor() {
            this.childNodes = [];
            this.parentNode = null;
        }

        get firstChild() {
            return this.childNodes[0] ?? null;
        }

        get nextSibling() {
            if (!this.parentNode) {
                return null;
            }
            const index = this.parentNode.childNodes.indexOf(this);
            return this.parentNode.childNodes[index + 1] ?? null;
        }

        get parentElement() {
            return this.parentNode instanceof FakeHTMLElement ? this.parentNode : null;
        }

        appendChild(child) {
            if (child.parentNode) {
                child.parentNode.removeChild(child);
            }
            this.childNodes.push(child);
            child.parentNode = this;
            return child;
        }

        insertBefore(child, reference) {
            if (child.parentNode) {
                child.parentNode.removeChild(child);
            }
            if (reference === null) {
                return this.appendChild(child);
            }
            const index = this.childNodes.indexOf(reference);
            assert.notEqual(index, -1);
            this.childNodes.splice(index, 0, child);
            child.parentNode = this;
            return child;
        }

        removeChild(child) {
            const index = this.childNodes.indexOf(child);
            assert.notEqual(index, -1);
            this.childNodes.splice(index, 1);
            child.parentNode = null;
            return child;
        }

        remove() {
            assert.ok(this.parentNode);
            this.parentNode.removeChild(this);
        }

        hasChildNodes() {
            return this.childNodes.length > 0;
        }
    }

    class FakeHTMLElement extends FakeNode {
        constructor(tagName) {
            super();
            this.tagName = tagName.toUpperCase();
            this.attributes = new Map();
        }

        cloneNode(deep) {
            assert.equal(deep, false);
            const clone = new FakeHTMLElement(this.tagName);
            clone.attributes = new Map(this.attributes);
            return clone;
        }

        removeAttribute(name) {
            this.attributes.delete(name);
        }
    }

    class FakeText extends FakeNode {
        constructor(data) {
            super();
            this.data = data;
        }

        splitText(offset) {
            const trailingText = new FakeText(this.data.slice(offset));
            this.data = this.data.slice(0, offset);
            assert.ok(this.parentNode);
            this.parentNode.insertBefore(trailingText, this.nextSibling);
            return trailingText;
        }
    }

    globalThis.HTMLElement = FakeHTMLElement;
    globalThis.NodeFilter = { SHOW_TEXT: 4 };
    globalThis.document = {
        createTreeWalker(root) {
            const textNodes = [];
            const visit = (node) => {
                if (node instanceof FakeText) {
                    textNodes.push(node);
                    return;
                }
                for (const child of node.childNodes) {
                    visit(child);
                }
            };
            visit(root);
            let index = -1;
            return {
                nextNode() {
                    index += 1;
                    return textNodes[index] ?? null;
                },
            };
        },
    };

    try {
        const noteContent = new FakeHTMLElement('div');
        const paragraphs = [38, 21, 164, 104].map((length) => {
            const paragraph = new FakeHTMLElement('p');
            const bold = new FakeHTMLElement('strong');
            bold.attributes.set('style', 'font-weight: bold');
            bold.appendChild(new FakeText('x'.repeat(length)));
            paragraph.appendChild(bold);
            noteContent.appendChild(paragraph);
            return paragraph;
        });

        removeInlineFormattingFromTextSegments(noteContent, [
            { start: 0, end: 38 },
            { start: 38, end: 59 },
            { start: 59, end: 223 },
            { start: 223, end: 327 },
        ]);
        assert.deepEqual(noteContent.childNodes, paragraphs);
        for (const paragraph of paragraphs) {
            assert.equal(paragraph.childNodes.length, 1);
            assert.ok(paragraph.firstChild instanceof FakeText);
        }
    } finally {
        globalThis.document = originalDocument;
        globalThis.HTMLElement = originalHTMLElement;
        globalThis.NodeFilter = originalNodeFilter;
    }
});
