/**
 * T-SQL function mappings for MSSQL formula evaluation.
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
  // T-SQL TRIM (SQL Server 2017+) only strips space by default in older
  // dialects inconsistently; LTRIM(RTRIM()) works on all supported versions.
  TRIM: async (args: MapFnArgs) => {
    const x = (await args.fn(args.pt.arguments[0])).builder;
    return { builder: args.knex.raw(`LTRIM(RTRIM(?))`, [x]) };
  },
  SQRT: 'SQRT',
  ROUND: 'ROUND',
  NOW: 'GETDATE',
  ABS: 'ABS',
  CEILING: 'CEILING',
  FLOOR: 'FLOOR',
  POWER: 'POWER',
  MIN: 'MIN',
  MAX: 'MAX',
  LEFT: 'LEFT',
  RIGHT: 'RIGHT',
  // Product formulas use IF / ISBLANK; expose COALESCE for any raw CallExpression.
  COALESCE: async (args: MapFnArgs) => {
    const parts = await Promise.all(
      args.pt.arguments.map(async (d) => (await args.fn(d)).builder),
    );
    const placeholders = parts.map(() => '?').join(',');
    return {
      builder: args.knex.raw(`COALESCE(${placeholders})`, parts),
    };
  },
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
