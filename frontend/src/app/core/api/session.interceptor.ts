import { HttpErrorResponse, HttpInterceptorFn, HttpResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, tap, throwError } from 'rxjs';

/**
 * Bridges Angular's HttpClient to the existing Flask session-cookie auth.
 *
 * Three things this handles that plain HttpClient does not:
 *
 * 1. `withCredentials` + `X-Requested-With`. The Flask app authenticates with a
 *    server-side session cookie, so credentials must ride along. The extra
 *    header lets the backend tell an XHR apart from a browser navigation and
 *    return a 401 JSON body instead of a 302 redirect to the login page.
 *
 * 2. Redirects followed silently by XHR. When an unauthenticated XHR hits a
 *    protected route, Flask's `@app.before_request` guard answers with a 302 to
 *    /login. XHR follows that transparently, so the caller would receive a 200
 *    carrying an HTML login page. Treating an HTML response to a JSON request as
 *    an expired session turns that confusing case into a clean redirect.
 *
 * 3. Preserving the attempted URL so login can send the user back to it.
 */
export const sessionInterceptor: HttpInterceptorFn = (req, next) => {
  const router = inject(Router);

  const authorised = req.clone({
    withCredentials: true,
    setHeaders: {
      'X-Requested-With': 'XMLHttpRequest',
      Accept: 'application/json',
    },
  });

  return next(authorised).pipe(
    tap((event) => {
      if (event instanceof HttpResponse && isHtmlResponse(event)) {
        redirectToLogin(router, req.url);
      }
    }),
    catchError((err: unknown) => {
      if (err instanceof HttpErrorResponse) {
        if (err.status === 401 || isHtmlResponse(err)) {
          redirectToLogin(router, req.url);
        }
      }
      return throwError(() => err);
    }),
  );
};

function isHtmlResponse(res: { headers: { get(name: string): string | null } }): boolean {
  return res.headers.get('content-type')?.includes('text/html') ?? false;
}

function redirectToLogin(router: Router, attemptedUrl: string): void {
  // Guard against a redirect loop when the login page itself fails a request.
  if (router.url.startsWith('/login')) {
    return;
  }
  void router.navigate(['/login'], {
    queryParams: { returnUrl: attemptedUrl },
  });
}
