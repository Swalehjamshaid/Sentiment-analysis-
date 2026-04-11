@router.post("/register")
async def register_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Handles User Registration from HTML form.
    """
    if password != confirm_password:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"error": "Passwords do not match"}
        )

    email_clean = email.strip().lower()

    try:
        # Check for duplicate email
        result = await db.execute(select(User).where(User.email == email_clean))
        if result.scalars().first():
            return templates.TemplateResponse(
                request=request,
                name="register.html",
                context={"error": "This email is already registered."}
            )

        # Create new user - using only fields that likely exist in your model
        new_user = User(
            name=name.strip(),
            email=email_clean,
            hashed_password=get_password_hash(password)
            # Remove email_verified and is_active if they don't exist in your User model
        )

        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        logger.info(f"✅ New user registered: {email_clean}")

        # Create verification token and send email
        token = create_verification_token(new_user.email)

        try:
            await send_verification_email(new_user.email, token)
            success_msg = "Registration successful! Check your inbox for the magic login link."
        except Exception as e:
            logger.error(f"Email sending failed: {e}")
            success_msg = "Account created successfully. Verification email could not be sent."

        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"success": success_msg}
        )

    except Exception as e:
        await db.rollback()
        logger.error(f"❌ Registration Error: {str(e)}")
        logger.error(traceback.format_exc())
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"error": "Something went wrong. Please try again."}
        )
