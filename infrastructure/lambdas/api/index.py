"""Router for the authenticated app API.

Every route runs behind an API Gateway Cognito JWT authorizer, so the handler can
treat the email claim on the request as verified. Identity is taken from that
claim and nothing else, which is what keeps one user's documents, evaluations and
feedback out of another user's reach.
"""

import documents
import evaluations
import feedback
from common import BadRequest, Forbidden, caller_email, logger, response

ROUTES = {
    "GET /documents": documents.list_documents,
    "POST /documents/upload-url": documents.create_upload_url,
    "POST /documents/download-url": documents.create_download_url,
    "DELETE /documents": documents.delete_document,
    "POST /documents/sync": documents.sync_knowledge_base,
    "GET /documents/ingestion-status": documents.ingestion_status,

    "POST /evaluations": evaluations.create_evaluation,
    "GET /evaluations": evaluations.list_evaluations,
    "GET /evaluations/status": evaluations.evaluation_status,
    "GET /evaluations/results": evaluations.evaluation_results,

    "POST /feedback": feedback.submit_feedback,
}


def handler(event, _context):
    route = event.get("routeKey")
    try:
        email = caller_email(event)
        handle = ROUTES.get(route)
        if handle is None:
            return response(404, {"message": "Not found"})
        return handle(event, email)
    except BadRequest as exc:
        return response(400, {"message": str(exc)})
    except Forbidden as exc:
        logger.warning("Denied %s: %s", route, exc)
        return response(403, {"message": str(exc)})
    except Exception:
        # Detail stays in CloudWatch; the caller gets nothing it could probe with.
        logger.exception("Unhandled error on %s", route)
        return response(500, {"message": "Internal server error"})
