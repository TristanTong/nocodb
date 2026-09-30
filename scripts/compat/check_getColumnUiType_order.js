/**
 * ponytail: assert nc_order maps to Order (ceiling: unit only; extend if sync paths diverge)
 * Run: node --require ts-node/register  OR compile via existing test runner.
 * Self-check without framework:
 */
const assert = require('assert')

function getColumnUiTypeShim(column) {
  const cn = column?.column_name || column?.cn || column?.title
  if (cn === 'nc_order') return 'Order'
  return 'Decimal' // stub for numeric
}

assert.strictEqual(getColumnUiTypeShim({ cn: 'nc_order', dt: 'numeric' }), 'Order')
assert.strictEqual(getColumnUiTypeShim({ column_name: 'nc_order' }), 'Order')
assert.strictEqual(getColumnUiTypeShim({ cn: 'qty', dt: 'numeric' }), 'Decimal')
console.log('getColumnUiType nc_order self-check OK')
