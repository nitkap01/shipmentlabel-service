import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

// UX redirect only, not the security boundary — the backend re-verifies the
// session token on every request (see backend/app/security.py). This just
// avoids flashing a protected page before the API 401s.
export function middleware(request: NextRequest) {
  const hasSession = request.cookies.has('session')
  const isLoginPage = request.nextUrl.pathname === '/login'

  if (!hasSession && !isLoginPage) {
    return NextResponse.redirect(new URL('/login', request.url))
  }
  if (hasSession && isLoginPage) {
    return NextResponse.redirect(new URL('/', request.url))
  }
  return NextResponse.next()
}

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
}
