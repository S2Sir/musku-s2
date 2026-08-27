/**
 * backup-restore.test.js — Unit tests for Versioned Backup & 5-Step Restoration Validation
 */

(function (exports) {
  'use strict';

  function testBackupRestore(assert) {
    var backupMgr = globalThis.muskuBackup;
    assert.ok(backupMgr, 'muskuBackup instance should exist');

    var mockBackup = {
      format: 'MUSKU_BACKUP',
      version: 1,
      created_at: new Date().toISOString(),
      profile: { name: 'S2 Sir', title: 'Boss', language: 'hinglish' },
      persona: { relationship_mode: 'best_friend' },
      conversations: [{ conversation_id: 'c1', date_key: '2026-08-26', created_at: Date.now() }],
      messages: [],
      memory: [],
      projects: []
    };

    var check = backupMgr.validateBackupObject(mockBackup);
    assert.ok(check.valid, 'Valid versioned backup should pass 5-step validation');
    assert.equal(check.preview.conversationsCount, 1, 'Conversations count should match preview');

    var invalidCheck = backupMgr.validateBackupObject({ format: 'INVALID' });
    assert.equal(invalidCheck.valid, false, 'Invalid format should fail validation');
  }

  exports.testBackupRestore = testBackupRestore;
})(typeof exports !== 'undefined' ? exports : globalThis);
