import { pgTable, integer, text, timestamp, boolean, check } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { sql } from "drizzle-orm";
import { z } from "zod/v4";

// Single-row settings table — the CHECK constraint ensures only id=1 can exist.
export const appSettings = pgTable(
  "app_settings",
  {
    id: integer("id").primaryKey().default(1),
    loginEmail: text("login_email").notNull().default(""),
    loginEmailPassword: text("login_email_password").notNull().default(""),
    loginAccountPassword: text("login_account_password").notNull().default(""),
    enquiryEmail: text("enquiry_email").notNull().default(""),
    enquiryEmailPassword: text("enquiry_email_password").notNull().default(""),
    monitorEnabled: boolean("monitor_enabled").notNull().default(true),
    updatedAt: timestamp("updated_at").defaultNow(),
  },
  (t) => [check("single_row", sql`${t.id} = 1`)]
);

export const insertSettingsSchema = createInsertSchema(appSettings).omit({
  id: true,
  updatedAt: true,
});

export type AppSettings = typeof appSettings.$inferSelect;
export type InsertSettings = z.infer<typeof insertSettingsSchema>;
