import { notFound } from "next/navigation"
import { SupplierLedgerPage } from "@/components/inventory-admin/supplier-ledger-page"

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  const supplierId = Number(id)
  if (!/^[1-9]\d*$/.test(id) || !Number.isSafeInteger(supplierId)) notFound()
  return <SupplierLedgerPage id={supplierId} />
}
