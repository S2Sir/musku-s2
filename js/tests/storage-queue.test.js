/**
 * storage-queue.test.js — Unit tests for Non-Blocking Storage Write Queue
 */

(function (exports) {
  'use strict';

  function testStorageQueue(assert) {
    var queue = globalThis.muskuStorageQueue;
    assert.ok(queue, 'muskuStorageQueue instance should exist');

    var mockPayload = { message_id: 'msg_test_1', conversation_id: 'conv_1', role: 'user', content: 'Test enqueue', timestamp: Date.now() };
    queue.enqueue(0, 'SAVE_MESSAGE', mockPayload);
    assert.equal(queue.queue.length, 1, 'Queue length should be 1 after enqueue');
  }

  exports.testStorageQueue = testStorageQueue;
})(typeof exports !== 'undefined' ? exports : globalThis);
