import type Source from '~/models/Source';
import type Column from '~/models/Column';
import { UITypes, type ColumnType } from 'nocodb-sdk';
import ModelXcMetaFactory from '~/db/sql-mgr/code/models/xc/ModelXcMetaFactory';

export default function getColumnUiType(
  source: Source,
  column: Column | ColumnType | { cn?: string; column_name?: string },
) {
  // Physical sync maps numeric → Decimal; keep NocoDB row-order column as Order
  const cn =
    (column as any)?.column_name ||
    (column as any)?.cn ||
    (column as any)?.title;
  if (cn === 'nc_order') {
    return UITypes.Order;
  }

  const metaFact = ModelXcMetaFactory.create({ client: source.type }, {});
  return metaFact.getUIDataType(column);
}
