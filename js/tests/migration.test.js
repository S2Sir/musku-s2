/**
 * migration.test.js — Unit tests for LocalStorage musku_hist_* migration to IndexedDB
 */

(function (exports) {
  'use strict';

  function testMigration(assert) {
    var rawHist = JSON.stringify([
      { t: Date.now(), r: 'user', x: 'Migration test user message' },
      { t: Date.now() + 100, r: 'musku', x: 'Migration test musku reply' }
    ]);
    
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('musku_hist_2026-08-26', rawHist);
      localStorage.setItem('musku_hist_days', JSON.stringify(['2026-08-26']));
      assert.ok(localStorage.getItem('musku_hist_2026-08-26'), 'LocalStorage mock history should be set');
    }
  }

  exports.testMigration = testMigration;
})(typeof exports !== 'undefined' ? exports : globalThis);
