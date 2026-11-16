import { PurchaseOrderDocumentPage } from "@/components/inventory-admin/purchase-order-document-page"

export default async function PurchaseOrderDetailRoute({
  params,
}: {
  params: Promise<{ recordId: string }>
}) {
  const { recordId } = await params
  return <PurchaseOrderDocumentPage recordId={recordId} />
}
