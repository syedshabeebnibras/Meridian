"use server";

import { redirect } from "next/navigation";
import { AuthError } from "next-auth";
import { hash as hashArgon2 } from "@node-rs/argon2";
import { z } from "zod";

import { signIn } from "@/auth";
import { createUserAndPersonalWorkspace, findUserByEmail } from "@/lib/db";

const credentialsSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8).max(256),
  name: z.string().min(1).max(128).optional(),
});

export type AuthActionResult =
  | { ok: true }
  | { ok: false; error: string };

export async function signInAction(formData: FormData): Promise<AuthActionResult> {
  const parsed = credentialsSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password"),
  });
  if (!parsed.success) {
    return { ok: false, error: "Enter a valid email and password (8+ chars)." };
  }
  try {
    await signIn("credentials", {
      email: parsed.data.email,
      password: parsed.data.password,
      redirect: false,
    });
  } catch (err) {
    if (err instanceof AuthError) {
      return { ok: false, error: "Invalid email or password." };
    }
    throw err;
  }
  redirect("/chat");
}

export async function signUpAction(formData: FormData): Promise<AuthActionResult> {
  const parsed = credentialsSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password"),
    name: formData.get("name") ?? "",
  });
  if (!parsed.success) {
    return {
      ok: false,
      error: "Enter a valid email, a name, and a password of at least 8 characters.",
    };
  }

  const existing = await findUserByEmail(parsed.data.email);
  if (existing) {
    return { ok: false, error: "An account with that email already exists." };
  }

  const passwordHash = await hashArgon2(parsed.data.password);
  await createUserAndPersonalWorkspace({
    email: parsed.data.email,
    name: parsed.data.name ?? parsed.data.email.split("@")[0]!,
    passwordHash,
  });

  try {
    await signIn("credentials", {
      email: parsed.data.email,
      password: parsed.data.password,
      redirect: false,
    });
  } catch (err) {
    if (err instanceof AuthError) {
      return { ok: false, error: "Signed up but couldn't start a session. Try signing in." };
    }
    throw err;
  }
  redirect("/chat");
}
