/**
 * Minimal T-SQL function name mappings for MSSQL formula evaluation.
 * Unsupported functions are listed in MssqlUi.getUnsupportedFnList().
 */
import commonFns from './commonFns';
import type { MapFnArgs } from '~/db/mapFunctionName';

const mssql = {
  ...commonFns,
  LEN: 'LEN',
  LENGTH: 'LEN',
  LOWER: 'LOWER',
  UPPER: 'UPPER',
  TRIM: 'LTRIM',
  SQRT: 'SQRT',
  ROUND: 'ROUND',
  NOW: 'GETDATE',
  ABS: 'ABS',
  CEILING: 'CEILING',
  FLOOR: 'FLOOR',
  POWER: 'POWER',
  MIN: 'MIN',
  MAX: 'MAX',
  CONCAT: async (args: MapFnArgs) => {
    return {
      builder: args.knex.raw(
        `CONCAT(${(
          await Promise.all(
            args.pt.arguments.map(async (d) => (await args.fn(d)).builder),
          )
        )
          .map((d) => (typeof d === 'string' ? `'${d}'` : d))
          .join(',')})`,
      ),
    };
  },
};

export default mssql;
