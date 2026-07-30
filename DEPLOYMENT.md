# Deployment State

Last updated: 2026-07-30

## Deployment target

- Host: Render
- Service ID: `srv-d823urt0lvsc73ftmm40`
- Repository: `cirel94june/Lucien-Telegram-bot`
- No Fly.io copy is configured for Lucien

Runtime health can change with Render free-tier availability. Verify the Render dashboard before treating the service as live.

## Safety rules

1. Exactly one deployment may own this Telegram bot token at a time.
2. Do not copy Jasper's `fly.toml` or Fly webhook startup behavior into this repository unless Lucien is intentionally migrated.
3. The inactive-owner mention notification was removed on 2026-07-30. Do not restore it without an explicit request.
4. Jasper, Lucien, and Cloudy share an architecture, but changes must be reviewed and deployed per repository.
