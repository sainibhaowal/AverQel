import { redirect } from "next/navigation";

/**
 * Keep the organization namespace out of the dynamic document detail route.
 * Without this explicit index, `/documents/organization` is interpreted as a
 * document id and the detail client requests `/documents/organization/*`,
 * producing a cascade of UUID validation errors.
 */
export default function DocumentsOrganizationIndex() {
  redirect("/dashboard/documents/organization/tags");
}
