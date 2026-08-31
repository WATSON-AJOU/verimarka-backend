resource "aws_instance" "app" {
  ami                    = var.ec2_ami_id != null ? var.ec2_ami_id : data.aws_ami.amazon_linux_2023.id
  instance_type          = var.ec2_instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.app.id]
  key_name               = var.ec2_key_name
  iam_instance_profile   = aws_iam_instance_profile.app.name

  user_data                   = file("${path.module}/user_data.sh")
  user_data_replace_on_change = false

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.ec2_root_volume_size
    encrypted             = true
    delete_on_termination = true
  }

  tags = {
    Name = "${local.name}-app"
  }

  depends_on = [aws_iam_role_policy_attachment.ssm]
}

resource "aws_eip" "app" {
  domain   = "vpc"
  instance = aws_instance.app.id

  tags = {
    Name = "${local.name}-app-eip"
  }
}
