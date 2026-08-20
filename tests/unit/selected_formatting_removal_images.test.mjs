import assert from 'node:assert/strict';
import test from 'node:test';

import {
    findImagesIntersectingFormattingRemovalRange,
} from '../../app/static/js/modules/mode-manager/services/selected-formatting-removal-service.js';


test('selected formatting removal identifies only imagery inside the range', () => {
    const originalHTMLElement = globalThis.HTMLElement;
    const originalRange = globalThis.Range;

    class FakeHTMLElement {
        constructor(images = []) {
            this.images = images;
        }

        querySelectorAll(selector) {
            assert.equal(selector, 'img');
            return this.images;
        }
    }

    class FakeRange {
        constructor(selectedImages) {
            this.selectedImages = selectedImages;
        }

        intersectsNode(image) {
            return this.selectedImages.has(image);
        }
    }

    globalThis.HTMLElement = FakeHTMLElement;
    globalThis.Range = FakeRange;

    try {
        const selectedImage = new FakeHTMLElement();
        const outsideImage = new FakeHTMLElement();
        const noteContent = new FakeHTMLElement([selectedImage, outsideImage]);
        const selectedRange = new FakeRange(new Set([selectedImage]));

        assert.deepEqual(
            findImagesIntersectingFormattingRemovalRange(noteContent, selectedRange),
            [selectedImage],
        );
    } finally {
        if (typeof originalHTMLElement === 'undefined') {
            delete globalThis.HTMLElement;
        } else {
            globalThis.HTMLElement = originalHTMLElement;
        }
        if (typeof originalRange === 'undefined') {
            delete globalThis.Range;
        } else {
            globalThis.Range = originalRange;
        }
    }
});
