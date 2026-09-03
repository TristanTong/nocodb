import { NcErrorType } from 'nocodb-sdk';
import { DBError } from './utils';
import type { Logger } from '@nestjs/common';
import type { DBErrorExtractResult, IClientDbErrorExtractor } from './utils';

/**
 * Tedious / node-mssql typically surfaces RequestError with code `EREQUEST`
 * and SQL Server number in `error.number` / `error.originalError.info.number`.
 */
export class MssqlDBErrorExtractor implements IClientDbErrorExtractor {
  constructor(
    private readonly option?: {
      dbErrorLogger?: Logger;
    },
  ) {}

  private sqlNumber(error: any): number | undefined {
    const n =
      error?.number ??
      error?.originalError?.info?.number ??
      error?.precedingErrors?.[0]?.number;
    return typeof n === 'number' ? n : undefined;
  }

  extract(error: any): DBErrorExtractResult {
    if (!error?.code) return;

    const code = String(error.code);
    // Only handle MSSQL driver codes here
    if (
      ![
        'EREQUEST',
        'ELOGIN',
        'ETIMEOUT',
        'EALREADYCONNECTED',
        'EALREADYCONNECTING',
        'EINSTLOOKUP',
        'ESOCKET',
      ].includes(code)
    ) {
      return;
    }

    let message: string;
    let _extra: Record<string, any>;
    let _type: DBError;
    let httpStatus = 422;
    const num = this.sqlNumber(error);
    const rawMsg = String(error.message || error.originalError?.message || '');

    if (code === 'ELOGIN') {
      message = 'Failed to log in to SQL Server. Check user/password.';
      httpStatus = 400;
    } else if (code === 'ETIMEOUT' || code === 'ESOCKET') {
      message = 'SQL Server connection timed out or was reset.';
      httpStatus = 500;
    } else if (num === 208 || /Invalid object name/i.test(rawMsg)) {
      message = 'The table or object does not exist.';
      _type = DBError.TABLE_NOT_EXIST;
      const m = rawMsg.match(/Invalid object name '([^']+)'/i);
      if (m?.[1]) {
        message = `The table or object '${m[1]}' does not exist.`;
        _extra = { table: m[1] };
      }
    } else if (num === 2627 || num === 2601 || /unique|duplicate/i.test(rawMsg)) {
      message = 'This record already exists.';
      _type = DBError.UNIQUE_CONSTRAINT_VIOLATION;
    } else if (num === 515 || /Cannot insert the value NULL/i.test(rawMsg)) {
      message = 'Null value is not allowed for a required column.';
      _type = DBError.COLUMN_NOT_NULL;
      const m = rawMsg.match(/column '([^']+)'/i);
      if (m?.[1]) {
        message = `Null value is not allowed for column '${m[1]}'.`;
        _extra = { column: m[1] };
      }
    } else if (num === 547 || /REFERENCE constraint|FOREIGN KEY/i.test(rawMsg)) {
      message = 'This record is being referenced by other records.';
    } else if (num === 2705 || /already an object named|Column names in each table/i.test(rawMsg)) {
      message = 'The column already exists.';
      _type = DBError.COLUMN_EXIST;
    } else if (num === 2714 || /There is already an object named/i.test(rawMsg)) {
      message = 'The table already exists.';
      _type = DBError.TABLE_EXIST;
    } else if (num === 245 || /Conversion failed/i.test(rawMsg)) {
      message = 'Invalid data format for a column.';
      _type = DBError.DATA_TYPE_MISMATCH;
    } else {
      this.option?.dbErrorLogger?.error(
        `${code}${num != null ? `(${num})` : ''} is not handled on database mssql`,
      );
      message = rawMsg.includes('--')
        ? rawMsg.split('--')[1]
        : 'An error occurred when querying SQL Server.';
      httpStatus = 500;
    }

    return {
      error: NcErrorType.ERR_DATABASE_OP_FAILED,
      message,
      code: num != null ? `${code}:${num}` : code,
      httpStatus,
    };
  }
}
