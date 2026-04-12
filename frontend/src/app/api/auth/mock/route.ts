import { NextResponse } from "next/server";
import { SignJWT } from "jose";

export async function POST() {
  // strictly DEV ONLY backdoor (Temporarily allowed for Docker Pilot Testing)
  // if (process.env.NODE_ENV !== "development") {
  //   return NextResponse.json({ error: "Not Found" }, { status: 404 });
  // }

  const secretString = process.env.JWT_SECRET;
  if (!secretString) {
    return NextResponse.json({ error: "Missing JWT_SECRET in environment" }, { status: 500 });
  }

  const secret = new TextEncoder().encode(secretString);

  // Issue a 1-hour dev token for basic manual testing using HS256 as required by backend
  const alg = "HS256";
  const token = await new SignJWT({ sub: "finance_manager_1" })
    .setProtectedHeader({ alg, typ: "JWT" })
    .setIssuedAt()
    .setExpirationTime('1h')
    .sign(secret);

  return NextResponse.json({ access_token: token });
}
