from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import Analysis, LEVEL_CHOICES, GuestUsage, CVRebuild, CVCreation
from .serializers import AnalysisSerializer, CVRebuildSerializer, CVCreationSerializer
from .ai_service import analyze_cv, score_rewritten_cv, rewrite_cv, rebuild_cv, create_cv_from_scratch, generate_cover_letter, generate_cv_pdf, generate_cover_letter_pdf
from accounts.models import LEVEL_MIN_TIER, FREE_ANALYSES_LIMIT
from django.http import FileResponse
import json
import logging

logger = logging.getLogger(__name__)


def get_client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def extract_cv_text(cv_file):
    filename = (cv_file.name or '').lower()

    if filename.endswith('.pdf'):
        try:
            import PyPDF2
            pdf_reader = PyPDF2.PdfReader(cv_file)
            cv_text = ""
            for page in pdf_reader.pages:
                cv_text += page.extract_text()
            if not cv_text.strip():
                return None, 'Could not extract text from PDF.'
            return cv_text, None
        except Exception as e:
            return None, f'Failed to read PDF: {str(e)}'

    elif filename.endswith('.docx'):
        try:
            import docx
            document = docx.Document(cv_file)
            cv_text = "\n".join(p.text for p in document.paragraphs)
            if not cv_text.strip():
                return None, 'Could not extract text from Word document.'
            return cv_text, None
        except Exception as e:
            return None, f'Failed to read Word document: {str(e)}'

    elif filename.endswith('.doc'):
        return None, 'Older .doc files are not supported. Please save your CV as .docx or .pdf and try again.'

    else:
        return None, 'Unsupported file type. Please upload a PDF or Word (.docx) file.'


class AnalyzeView(APIView):
    """Runs the CV-vs-job-description match analysis only. Rewrite and
    cover letter are separate, later requests against the resulting
    Analysis id (see AnalysisExtraView), each gated and charged on its
    own. Credits/free-trial/guest-usage are only spent after the AI call
    succeeds, so a failed analysis never costs the user anything."""
    permission_classes = [AllowAny]

    def post(self, request):
        job_description = request.data.get('job_description')
        cv_file = request.FILES.get('cv_file')
        cv_text = request.data.get('cv_text')

        if not job_description:
            return Response({'error': 'job_description is required.'}, status=status.HTTP_400_BAD_REQUEST)

        if cv_file:
            cv_text, extraction_error = extract_cv_text(cv_file)
            if extraction_error:
                return Response({'error': extraction_error}, status=status.HTTP_400_BAD_REQUEST)
        elif not cv_text:
            return Response({'error': 'Either cv_file (PDF or DOCX) or cv_text is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Pre-flight eligibility checks only (no deduction yet). This lets
        # us reject up front without ever touching the AI provider, while
        # still not spending anything until the AI call actually succeeds.
        if request.user.is_authenticated:
            user = request.user
            if user.free_analyses_remaining <= 0 and user.analysis_credits < 1:
                return Response(
                    {'error': 'Your free analyses are used up. Purchase a plan to continue.', 'requires_purchase': True},
                    status=status.HTTP_402_PAYMENT_REQUIRED
                )
        else:
            ip = get_client_ip(request)
            guest_usage, _ = GuestUsage.objects.get_or_create(ip_address=ip)
            if guest_usage.analyses_used >= FREE_ANALYSES_LIMIT:
                return Response(
                    {'error': 'You have used your free analyses. Create a free account to continue.', 'requires_auth': True},
                    status=status.HTTP_402_PAYMENT_REQUIRED
                )

        # The AI call itself. Nothing is deducted until this succeeds.
        try:
            ai_result = analyze_cv(cv_text, job_description)
        except Exception as e:
            logger.exception("analyze_cv failed")
            return Response(
                {'error': 'CV analysis failed. Please try again.', 'detail': str(e)},
                status=status.HTTP_502_BAD_GATEWAY
            )

        used_free_trial = False
        if request.user.is_authenticated:
            user = request.user
            if user.free_analyses_remaining > 0:
                user.free_analyses_used += 1
                user.save(update_fields=['free_analyses_used'])
                used_free_trial = True
            else:
                user.analysis_credits -= 1
                user.save(update_fields=['analysis_credits'])

            analysis = Analysis.objects.create(
                user=request.user,
                cv_text=cv_text,
                job_description=job_description,
                match_score=ai_result['match_score'],
                score_breakdown=ai_result.get('score_breakdown'),
                matched_skills=ai_result['matched_skills'],
                missing_skills=ai_result['missing_skills'],
                improvement_tips=ai_result['improvement_tips'],
                summary=ai_result['summary'],
            )

            serializer = AnalysisSerializer(analysis)
            response_data = dict(serializer.data)
            response_data['analysis_credits'] = request.user.analysis_credits
            response_data['free_analyses_remaining'] = request.user.free_analyses_remaining
            response_data['used_free_trial'] = used_free_trial
            return Response(response_data, status=status.HTTP_201_CREATED)

        else:
            ip = get_client_ip(request)
            guest_usage, _ = GuestUsage.objects.get_or_create(ip_address=ip)
            guest_usage.analyses_used += 1
            guest_usage.save(update_fields=['analyses_used'])

            return Response({
                'id': None,
                'match_score': ai_result['match_score'],
                'score_breakdown': ai_result.get('score_breakdown'),
                'matched_skills': ai_result['matched_skills'],
                'missing_skills': ai_result['missing_skills'],
                'improvement_tips': ai_result['improvement_tips'],
                'summary': ai_result['summary'],
                'cv_rewrite_requested': False,
                'rewritten_cv': None,
                'cover_letter_requested': False,
                'cover_letter': None,
                'guest': True,
            }, status=status.HTTP_200_OK)


class AnalysisExtraView(APIView):
    """Request a CV rewrite or a cover letter for an existing Analysis,
    after the fact. Body: {"type": "rewrite" | "cover_letter", "level": "mid"}.
    Login required (guests never had access to this). Charged one credit,
    but only after the AI call succeeds — a failure costs nothing."""
    permission_classes = [IsAuthenticated]

    def post(self, request, id):
        extra_type = request.data.get('type')
        level = request.data.get('level')

        if extra_type not in ('rewrite', 'cover_letter'):
            return Response({'error': 'type must be "rewrite" or "cover_letter".'}, status=status.HTTP_400_BAD_REQUEST)

        if not level or level not in dict(LEVEL_CHOICES):
            return Response({'error': 'A valid level (entry, mid, senior, executive) is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            analysis = Analysis.objects.get(id=id, user=request.user)
        except Analysis.DoesNotExist:
            return Response({'error': 'Analysis not found.'}, status=status.HTTP_404_NOT_FOUND)

        user = request.user

        if level not in user.unlocked_levels():
            return Response(
                {'error': f'Your current plan does not include the {level} level. Upgrade your plan to unlock it.', 'requires_upgrade': True},
                status=status.HTTP_403_FORBIDDEN
            )

        if user.analysis_credits < 1:
            return Response(
                {'error': 'You are out of credits. Purchase or top up a plan to continue.', 'requires_purchase': True},
                status=status.HTTP_402_PAYMENT_REQUIRED
            )

        if extra_type == 'rewrite':
            try:
                rewritten = rewrite_cv(
                    analysis.cv_text, analysis.job_description,
                    analysis.matched_skills, analysis.missing_skills,
                    analysis.improvement_tips, level=level
                )
                rewritten_result = score_rewritten_cv(rewritten, analysis.job_description)
            except Exception as e:
                logger.exception("rewrite_cv failed")
                return Response(
                    {'error': 'CV rewrite failed. Please try again.', 'detail': str(e)},
                    status=status.HTTP_502_BAD_GATEWAY
                )

            user.analysis_credits -= 1
            user.save(update_fields=['analysis_credits'])

            analysis.cv_rewrite_requested = True
            analysis.rewritten_cv = rewritten
            analysis.rewritten_match_score = rewritten_result.get('match_score')
            analysis.rewritten_score_breakdown = rewritten_result.get('score_breakdown')
            analysis.rewrite_level = level
            analysis.save()

        else:  # cover_letter
            try:
                cover_letter = generate_cover_letter(
                    analysis.cv_text, analysis.job_description,
                    analysis.matched_skills, analysis.improvement_tips, level=level
                )
            except Exception as e:
                logger.exception("generate_cover_letter failed")
                return Response(
                    {'error': 'Cover letter generation failed. Please try again.', 'detail': str(e)},
                    status=status.HTTP_502_BAD_GATEWAY
                )

            user.analysis_credits -= 1
            user.save(update_fields=['analysis_credits'])

            analysis.cover_letter_requested = True
            analysis.cover_letter = cover_letter
            analysis.cover_letter_level = level
            analysis.save()

        serializer = AnalysisSerializer(analysis)
        response_data = dict(serializer.data)
        response_data['analysis_credits'] = user.analysis_credits
        return Response(response_data, status=status.HTTP_200_OK)


class RebuildCVView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        level = request.data.get('level', 'mid')
        cv_file = request.FILES.get('cv_file')
        cv_text = request.data.get('cv_text')

        if cv_file:
            cv_text, extraction_error = extract_cv_text(cv_file)
            if extraction_error:
                return Response({'error': extraction_error}, status=status.HTTP_400_BAD_REQUEST)
        elif not cv_text:
            return Response({'error': 'Either cv_file (PDF or DOCX) or cv_text is required.'}, status=status.HTTP_400_BAD_REQUEST)

        if level not in dict(LEVEL_CHOICES):
            return Response({'error': 'A valid level (entry, mid, senior, executive) is required.'}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user

        if level not in user.unlocked_levels():
            return Response(
                {'error': f'Your current plan does not include the {level} level. Upgrade your plan to unlock it.', 'requires_upgrade': True},
                status=status.HTTP_403_FORBIDDEN
            )

        if user.analysis_credits < 1:
            return Response(
                {'error': 'You are out of credits. Purchase or top up a plan to continue.', 'requires_purchase': True},
                status=status.HTTP_402_PAYMENT_REQUIRED
            )

        try:
            rebuilt = rebuild_cv(cv_text, level=level)
        except Exception as e:
            logger.exception("rebuild_cv failed")
            return Response({'error': 'CV rebuild failed. Please try again.', 'detail': str(e)}, status=status.HTTP_502_BAD_GATEWAY)

        user.analysis_credits -= 1
        user.save(update_fields=['analysis_credits'])

        rebuild_record = CVRebuild.objects.create(
            user=user,
            original_cv_text=cv_text,
            rebuilt_cv=rebuilt,
            level=level,
        )

        serializer = CVRebuildSerializer(rebuild_record)
        response_data = dict(serializer.data)
        response_data['analysis_credits'] = user.analysis_credits
        return Response(response_data, status=status.HTTP_201_CREATED)


class CreateCVView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        level = request.data.get('level', 'mid')
        raw_data = request.data.get('data')
        reference_file = request.FILES.get('reference_cv_file')

        if not raw_data:
            return Response({'error': 'data is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            data = json.loads(raw_data)
        except (TypeError, ValueError):
            return Response({'error': 'data must be valid JSON.'}, status=status.HTTP_400_BAD_REQUEST)

        if not data.get('full_name') or not data.get('email'):
            return Response({'error': 'full_name and email are required.'}, status=status.HTTP_400_BAD_REQUEST)

        if level not in dict(LEVEL_CHOICES):
            return Response({'error': 'A valid level (entry, mid, senior, executive) is required.'}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user

        if level not in user.unlocked_levels():
            return Response(
                {'error': f'Your current plan does not include the {level} level. Upgrade your plan to unlock it.', 'requires_upgrade': True},
                status=status.HTTP_403_FORBIDDEN
            )

        if user.analysis_credits < 1:
            return Response(
                {'error': 'You are out of credits. Purchase or top up a plan to continue.', 'requires_purchase': True},
                status=status.HTTP_402_PAYMENT_REQUIRED
            )

        reference_cv_text = None
        if reference_file:
            reference_cv_text, extraction_error = extract_cv_text(reference_file)
            if extraction_error:
                return Response({'error': extraction_error}, status=status.HTTP_400_BAD_REQUEST)

        try:
            generated = create_cv_from_scratch(data, level=level, reference_cv_text=reference_cv_text)
        except Exception as e:
            logger.exception("create_cv_from_scratch failed")
            return Response({'error': 'CV creation failed. Please try again.', 'detail': str(e)}, status=status.HTTP_502_BAD_GATEWAY)

        user.analysis_credits -= 1
        user.save(update_fields=['analysis_credits'])

        creation = CVCreation.objects.create(
            user=user,
            full_name=data.get('full_name', ''),
            email=data.get('email', ''),
            phone=data.get('phone', ''),
            location=data.get('location', ''),
            linkedin=data.get('linkedin', ''),
            portfolio=data.get('portfolio', ''),
            professional_summary=data.get('professional_summary', ''),
            work_experience=data.get('work_experience', []),
            education=data.get('education', []),
            skills=data.get('skills', []),
            projects=data.get('projects', []),
            certifications=data.get('certifications', []),
            achievements=data.get('achievements', []),
            reference_cv_text=reference_cv_text,
            level=level,
            generated_cv=generated,
        )

        serializer = CVCreationSerializer(creation)
        response_data = dict(serializer.data)
        response_data['analysis_credits'] = user.analysis_credits
        return Response(response_data, status=status.HTTP_201_CREATED)


class DownloadCreatedCVView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            creation = CVCreation.objects.get(id=id, user=request.user)
            pdf_buffer = generate_cv_pdf(creation.generated_cv, creation.full_name)
            return FileResponse(pdf_buffer, as_attachment=True, filename=f"CVX_{creation.full_name.replace(' ', '_')}.pdf", content_type='application/pdf')
        except CVCreation.DoesNotExist:
            return Response({'error': 'CV not found.'}, status=status.HTTP_404_NOT_FOUND)


class AnalysisHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        analyses = Analysis.objects.filter(user=request.user).order_by('-created_at')
        serializer = AnalysisSerializer(analyses, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AnalysisDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            analysis = Analysis.objects.get(id=id, user=request.user)
            serializer = AnalysisSerializer(analysis)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Analysis.DoesNotExist:
            return Response({'error': 'Analysis not found.'}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, id):
        try:
            analysis = Analysis.objects.get(id=id, user=request.user)
            analysis.delete()
            return Response({'message': 'Analysis deleted successfully.'}, status=status.HTTP_200_OK)
        except Analysis.DoesNotExist:
            return Response({'error': 'Analysis not found.'}, status=status.HTTP_404_NOT_FOUND)


class DownloadRewrittenCVView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            analysis = Analysis.objects.get(id=id, user=request.user)
            if not analysis.rewritten_cv:
                return Response({'error': 'No rewritten CV found.'}, status=status.HTTP_404_NOT_FOUND)
            full_name = f"{request.user.first_name} {request.user.last_name}"
            pdf_buffer = generate_cv_pdf(analysis.rewritten_cv, full_name)
            return FileResponse(pdf_buffer, as_attachment=True, filename=f"CVX_{full_name.replace(' ', '_')}.pdf", content_type='application/pdf')
        except Analysis.DoesNotExist:
            return Response({'error': 'Analysis not found.'}, status=status.HTTP_404_NOT_FOUND)


class DownloadRebuiltCVView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            rebuild_record = CVRebuild.objects.get(id=id, user=request.user)
            full_name = f"{request.user.first_name} {request.user.last_name}"
            pdf_buffer = generate_cv_pdf(rebuild_record.rebuilt_cv, full_name)
            return FileResponse(pdf_buffer, as_attachment=True, filename=f"CVX_Rebuilt_{full_name.replace(' ', '_')}.pdf", content_type='application/pdf')
        except CVRebuild.DoesNotExist:
            return Response({'error': 'Rebuild not found.'}, status=status.HTTP_404_NOT_FOUND)


class DownloadCoverLetterView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            analysis = Analysis.objects.get(id=id, user=request.user)
            if not analysis.cover_letter:
                return Response({'error': 'No cover letter found.'}, status=status.HTTP_404_NOT_FOUND)
            full_name = f"{request.user.first_name} {request.user.last_name}"
            pdf_buffer = generate_cover_letter_pdf(analysis.cover_letter, full_name)
            return FileResponse(pdf_buffer, as_attachment=True, filename=f"CVX_CoverLetter_{full_name.replace(' ', '_')}.pdf", content_type='application/pdf')
        except Analysis.DoesNotExist:
            return Response({'error': 'Analysis not found.'}, status=status.HTTP_404_NOT_FOUND)